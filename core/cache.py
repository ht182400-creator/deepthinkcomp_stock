# -*- coding: utf-8 -*-
"""
TTL 缓存 + 降级缓存（stale-while-revalidate）。
- 命中且未过期 → 返回
- 过期但有值 → 返回旧值（降级缓存，后台不自动刷新，由调用方决定）
- 未命中 → fetcher() 拉取并写入
线程安全。
"""
import json
import os
import threading
import time


class TtlCache:
    def __init__(self, ttl: float = 30):
        self.ttl = ttl
        self._data = {}
        self._ts = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        """命中返回 value；过期/未命中返回 None"""
        with self._lock:
            v = self._data.get(key)
            ts = self._ts.get(key)
            if v is None or ts is None:
                return None
            if time.time() - ts > self.ttl:
                return None   # 过期
            return v

    def get_stale(self, key: str):
        """降级缓存：即使过期也返回旧值（数据源全挂时兜底）"""
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value
            self._ts[key] = time.time()

    def get_or_set(self, key: str, fetcher):
        """缓存未命中则 fetcher() 拉取。返回 (value, from_cache)"""
        v = self.get(key)
        if v is not None:
            return v, True
        v = fetcher()
        self.set(key, v)
        return v, False

    def invalidate(self, key: str):
        with self._lock:
            self._data.pop(key, None)
            self._ts.pop(key, None)


class FileCache:
    """JSON 文件缓存（大数组，如分钟 K 线）。TTL 内有效。"""

    def __init__(self, dir_path: str, default_ttl: float = 3600 * 24):
        self.dir = dir_path
        self.ttl = default_ttl
        os.makedirs(dir_path, exist_ok=True)

    def _path(self, key: str) -> str:
        # key 安全化：code_period
        safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return os.path.join(self.dir, safe + ".json")

    def get(self, key: str, max_age_s: float = None):
        p = self._path(key)
        # 显式 max_age_s=0 是合法值（强制过期），不能与「未指定」混淆
        max_age_s = self.ttl if max_age_s is None else max_age_s
        try:
            if os.path.exists(p) and time.time() - os.path.getmtime(p) < max_age_s:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def get_stale(self, key: str):
        p = self._path(key)
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def invalidate(self, key: str):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def set(self, key: str, value):
        try:
            with open(self._path(key), "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False)
        except Exception:
            pass
