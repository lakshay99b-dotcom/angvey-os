"""Angvey Agent OS — self-contained Vercel serverless API."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
import urllib.parse
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Angvey Agent OS", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODELS = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"]


def _unwrap_ddg(href: str) -> str:
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs:
        return urllib.parse.unquote(qs["uddg"][0])
    return href


def web_search(query: str, max_results: int = 5) -> list:
    max_results = max(1, min(int(max_results or 5), 8))
    results, errors = [], []
    try:
        q = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={q}"
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": UA})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select("div.result, div.results_links, div.web-result"):
            a = item.select_one("a.result__a, a.result-link, a[href]")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = _unwrap_ddg(a.get("href", ""))
            sn = item.select_one("a.result__snippet, div.result__snippet, td.result-snippet")
            snippet = sn.get_text(" ", strip=True) if sn else ""
            if title and href.startswith("http"):
                results.append({"title": title, "url": href, "snippet": snippet, "source": "ddg"})
            if len(results) >= max_results:
                break
        if not results:
            for a in soup.select("a.result__a"):
                title = a.get_text(strip=True)
                href = _unwrap_ddg(a.get("href", ""))
                if title and href.startswith("http"):
                    results.append({"title": title, "url": href, "snippet": "", "source": "ddg"})
                if len(results) >= max_results:
                    break
    except Exception as e:
        errors.append(f"ddg: {e}")
    if len(results) < max_results:
        try:
            api = "https://en.wikipedia.org/w/api.php"
            params = {"action": "query", "list": "search", "srsearch": query, "srlimit": max_results, "format": "json"}
            with httpx.Client(timeout=15) as client:
                resp = client.get(api, params=params, headers={"User-Agent": UA})
                resp.raise_for_status()
                data = resp.json()
            for item in data.get("query", {}).get("search", []):
                title = item.get("title", "")
                page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                if not any(r.get("url") == page_url for r in results):
                    results.append({"title": title, "url": page_url, "snippet": snippet, "source": "wikipedia"})
        except Exception as e:
            errors.append(f"wiki: {e}")
    if not results and errors:
        raise RuntimeError("Search failed: " + "; ".join(errors))
    return results[:max_results]


def fetch_webpage(url: str, max_chars: int = 4000) -> dict:
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": UA})
        resp.raise_for_status()
        html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        tag.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else "") or url
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
    return {"url": url, "title": title, "content": text, "chars": len(text)}


TOOLS = {
    "web_search": {
        "schema": {"type": "function", "function": {"name": "web_search", "description": "Search the web", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 5}}, "required": ["query"]}}},
        "fn": web_search,
    },
    "fetch_webpage": {
        "schema": {"type": "function", "function": {"name": "fetch_webpage", "description": "Fetch webpage text", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer", "default": 4000}}, "required": ["url"]}}},
        "fn": fetch_webpage,
    },
}


def tool_schemas():
    return [t["schema"] for t in TOOLS.values()]


def run_tool(name: str, args: dict) -> dict:
    entry = TOOLS.get(name)
    if not entry:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return {"ok": True, "output": entry["fn"](**(args or {}))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def groq_chat(messages, tools=None, max_tokens=800):
    from groq import Groq
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise ValueError("GROQ_API_KEY not set")
    client = Groq(api_key=key)
    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    kwargs = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    last_err = None
    for m in [model] + [x for x in FALLBACK_MODELS if x != model]:
        try:
            kwargs["model"] = m
            completion = client.chat.completions.create(**kwargs)
            choice = completion.choices[0]
            msg = choice.message
            tool_calls = []
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({"id": tc.id or str(uuid.uuid4()), "name": tc.function.name, "arguments": args})
            usage = {}
            if completion.usage:
                usage = {"prompt_tokens": completion.usage.prompt_tokens or 0, "completion_tokens": completion.usage.completion_tokens or 0, "total_tokens": completion.usage.total_tokens or 0}
            return {"content": msg.content, "tool_calls": tool_calls, "usage": usage, "model": m}
        except Exception as e:
            last_err = e
            if "model" in str(e).lower() and ("not found" in str(e).lower() or "does not exist" in str(e).lower()):
                continue
            raise
    raise last_err or RuntimeError("Groq failed")


SYSTEM = "You are Angvey, a model-agnostic Agent OS. Plan, use tools, observe, then deliver a clear final answer. Prefer web_search (1-2 queries). Optionally fetch_webpage. Cite sources. When done, final answer with no more tools."


def run_agent(goal: str, max_iters: int = 6) -> dict:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Goal: {goal}\n\nExecute using tools if needed. When finished, give a final answer."}]
    events, tool_calls_log = [], []
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    model_used = None
    schemas = tool_schemas()
    for i in range(max_iters):
        events.append({"kind": "iteration", "detail": i + 1})
        try:
            resp = groq_chat(messages, tools=schemas, max_tokens=800)
        except Exception as e:
            err = str(e)
            events.append({"kind": "error", "detail": err[:400]})
            if "429" in err or "rate" in err.lower():
                time.sleep(2 + i)
                continue
            return {"task_id": str(uuid.uuid4()), "status": "failed", "result": f"Model error: {err}", "tool_calls": tool_calls_log, "tokens": tokens, "errors": [err[:300]], "model": model_used, "events": events[-20:]}
        model_used = resp.get("model")
        for k in tokens:
            tokens[k] += (resp.get("usage") or {}).get(k, 0)
        if resp.get("content"):
            events.append({"kind": "thought", "detail": (resp["content"] or "")[:300]})
        tcs = resp.get("tool_calls") or []
        if tcs:
            asst = {"role": "assistant", "content": resp.get("content")}
            asst["tool_calls"] = [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments") or {})}} for tc in tcs]
            messages.append(asst)
            for tc in tcs:
                name, args = tc["name"], tc.get("arguments") or {}
                events.append({"kind": "tool_call", "detail": {"name": name, "arguments": args}})
                result = run_tool(name, args)
                tool_calls_log.append({"name": name, "arguments": args, "ok": result.get("ok")})
                events.append({"kind": "tool_result", "detail": {"name": name, "ok": result.get("ok"), "preview": str(result.get("output") or result.get("error"))[:200]}})
                payload = result.get("output") if result.get("ok") else {"error": result.get("error")}
                content = json.dumps(payload, ensure_ascii=False, default=str)
                if len(content) > 3500:
                    content = content[:3500] + "…[truncated]"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": content})
            continue
        final = (resp.get("content") or "").strip() or "Completed."
        events.append({"kind": "complete", "detail": final[:300]})
        return {"task_id": str(uuid.uuid4()), "status": "completed", "result": final, "tool_calls": tool_calls_log, "tokens": tokens, "errors": [], "model": model_used, "events": events[-20:]}
    return {"task_id": str(uuid.uuid4()), "status": "failed", "result": "Max iterations reached.", "tool_calls": tool_calls_log, "tokens": tokens, "errors": ["MAX_ITERATIONS"], "model": model_used, "events": events[-20:]}


class RunRequest(BaseModel):
    goal: str
    mock: bool = False
    max_iters: int = 6


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "service": "angvey-agent-os", "version": "0.2.0", "has_groq_key": bool(os.environ.get("GROQ_API_KEY"))}


@app.get("/api/tools")
def list_tools():
    return {"tools": list(TOOLS.keys()), "schemas": tool_schemas()}


@app.post("/api/agent/run")
def agent_run(req: RunRequest):
    if req.mock:
        return {"task_id": str(uuid.uuid4()), "status": "completed", "result": f"[mock] Acknowledged: {req.goal[:200]}", "tool_calls": [], "tokens": {}, "errors": [], "model": "mock", "events": [{"kind": "mock", "detail": "skipped"}]}
    return run_agent(req.goal, max_iters=min(req.max_iters, 8))
