from __future__ import annotations
import base64
import time
import subprocess
import tempfile
from dataclasses import dataclass
import os
from typing import Any, Dict, List
from pathlib import Path
import requests
from loguru import logger

@dataclass
class OCRResult:
    text: str
    conf: float | None = None
    box: Any | None = None

class HttpUmiOCRClient:
    """(备用) 与 Umi OCR 桌面版 HTTP 服务交互的客户端。"""

    def __init__(self, base_url: str = "http://127.0.0.1:1224", timeout: float = 30.0, retry: int = 2, backoff: float = 1.5):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry = retry
        self.backoff = backoff

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        last_err: Exception | None = None
        for attempt in range(self.retry + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning(f"HTTP 调用失败 {url} attempt={attempt+1}: {e}")
                if attempt < self.retry:
                    time.sleep(self.backoff ** (attempt + 1))
        raise RuntimeError(f"请求 {url} 失败: {last_err}")

    def ocr_image(self, image_path: str | Path) -> List[OCRResult]:
        p = Path(image_path)
        if not p.is_file():
            raise FileNotFoundError(p)
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode('utf-8')
        payload = {"image_base64": b64}
        raw = self._post("/api/ocr", payload)
        if raw.get("code") not in (0, 200):
            logger.error(f"OCR 服务返回错误: {raw}")
            return []
        items = raw.get("data") or []
        results: List[OCRResult] = []
        for it in items:
            text = it.get("text") or ""
            score = it.get("score")
            box = it.get("box")
            results.append(OCRResult(text=text, conf=score, box=box))
        return results


class CommandUmiOCRClient:
    """通过命令行调用 Umi-OCR 可执行文件。

    mode:
        - file (默认): 使用 --output 临时文件（官方最稳定）
        - stdout: 不加输出参数, 直接解析 stdout (可能受版本限制, 失败则回退 file)
        - clip: 使用 --clip 复制到剪贴板，再读取（需要 pyperclip）
    """

    NOISE_PREFIXES = {"Umi-OCR", "Umi-OCR hide."}
    PLACEHOLDER_SUBSTRINGS = ["No text in OCR result", "No text", "[Message]"]

    def __init__(
        self,
        exe_path: str = "Umi-OCR.exe",
        timeout: float = 60.0,
        extra_args: List[str] | None = None,
        hide: bool = False,
        mode: str = "file",
        enforce_utf8: bool = True,
    ):
        self.exe_path = exe_path
        self.timeout = timeout
        self.extra_args = extra_args or []
        self.hide = hide
        self.mode = mode if mode in {"file", "stdout", "clip"} else "file"
        self.enforce_utf8 = enforce_utf8

    def ocr_image(self, image_path: str | Path) -> List[OCRResult]:
        p = Path(image_path)
        if not p.is_file():
            raise FileNotFoundError(p)
        text_content = ""
        used_mode = self.mode
        if self.mode == "file":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tf:
                out_path = Path(tf.name)
            cmd = [self.exe_path, "--path", str(p), "--output", str(out_path), *self.extra_args]
            if self.hide:
                cmd.append("--hide")
            logger.debug(f"执行命令(file): {' '.join(map(str, cmd))}")
            proc = self._run(cmd)
            if proc is None:
                return []
            try:
                text_content = out_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:  # noqa: BLE001
                logger.warning(f"读取输出文件失败 {out_path}: {e}")
            finally:
                try:
                    out_path.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
        elif self.mode == "stdout":
            cmd = [self.exe_path, "--path", str(p), *self.extra_args]
            if self.hide:
                cmd.append("--hide")
            logger.debug(f"执行命令(stdout): {' '.join(map(str, cmd))}")
            proc = self._run(cmd)
            if proc is None:
                return []
            text_content = (proc.stdout or "") + "\n" + (proc.stderr or "")
            # 如果 stdout 模式拿不到有效内容，自动回退 file
            if not text_content.strip():
                used_mode = "file"
                self.mode = "file"
                return self.ocr_image(p)  # 递归一次
        elif self.mode == "clip":
            cmd = [self.exe_path, "--path", str(p), "--clip", *self.extra_args]
            if self.hide:
                cmd.append("--hide")
            logger.debug(f"执行命令(clip): {' '.join(map(str, cmd))}")
            proc = self._run(cmd)
            if proc is None:
                return []
            try:
                import pyperclip  # type: ignore
                text_content = pyperclip.paste() or ""
            except Exception as e:  # noqa: BLE001
                logger.warning(f"读取剪贴板失败: {e}")
                return []
        else:  # 安全兜底
            self.mode = "file"
            return self.ocr_image(p)

        # 过滤占位或噪声
        lines: List[str] = []
        for ln in text_content.splitlines():
            t = ln.strip()
            if not t:
                continue
            if any(t.startswith(pref) for pref in self.NOISE_PREFIXES):
                continue
            if any(sub in t for sub in self.PLACEHOLDER_SUBSTRINGS):
                continue
            lines.append(t)

        if not lines:  # 无有效文本
            logger.debug(f"{p} {used_mode} 模式无有效文本输出")
            return []
        return [OCRResult(text=ln) for ln in lines]

    def _run(self, cmd: List[str]):
        try:
            # 构造环境，必要时强制 UTF-8，避免下游 Python 程序在 GBK 控制台下打印非 GBK 字符崩溃
            env = None
            if self.enforce_utf8:
                env = os.environ.copy()
                # PYTHONUTF8=1 启用 UTF-8 模式；PYTHONIOENCODING 确保 stdout/stderr 使用 utf-8
                env.setdefault("PYTHONUTF8", "1")
                env.setdefault("PYTHONIOENCODING", "utf-8")
                # 一些程序会参考 LANG / LC_ALL
                env.setdefault("LANG", "C.UTF-8")
                env.setdefault("LC_ALL", "C.UTF-8")
                # Windows 终端代码页不一定被改变，但子进程 Python 会转为 UTF-8
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                encoding="utf-8",
                errors="replace",  # 避免因个别字节解码失败整体报错
            )
        except FileNotFoundError:  # noqa: BLE001
            logger.error(f"找不到 Umi-OCR 可执行文件: {self.exe_path}")
            return None
        except subprocess.TimeoutExpired:  # noqa: BLE001
            logger.error(f"Umi-OCR 调用超时: {' '.join(cmd)}")
            return None
        if proc.returncode != 0:
            logger.warning(f"Umi-OCR 返回码 {proc.returncode}: {proc.stderr.strip()}")
        return proc

    def batch_ocr(self, image_paths: List[str | Path]) -> Dict[str, List[OCRResult]]:
        # 可改进：一次性传多个路径。但为保证逐图文本拆分准确，此处循环。
        return {str(p): self.ocr_image(p) for p in image_paths}

