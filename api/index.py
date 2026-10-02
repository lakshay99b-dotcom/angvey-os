from __future__ import annotations
import json, os, re, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Angvey Agent OS", version="0.4.3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
HEADERS = {"User-Agent": "AngveyResearchBot/0.4.3", "Accept": "application/json"}
HTML_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36"}
WIKI_HEADERS = {"User-Agent": "AngveyResearchBot/0.4.3 (public research; https://angvey-agent.vercel.app)"}
DEFAULT_MODEL = "qwen/qwen3.8-27b"
FALLBACK_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

OFFICIAL_DOCS = {
    "langgraph": [{"title": "LangGraph docs", "url": "https://docs.langchain.com/oss/python/langgraph/overview", "blurb": "Graph agent orchestration"}],
    "crewai": [{"title": "CrewAI Docs", "url": "https://docs.crewai.com/", "blurb": "Crews and flows"}],
    "autogen": [{"title": "AutoGen Docs", "url": "https://microsoft.github.io/autogen/", "blurb": "Multi-agent framework"}],
}

PATTERN_LIBRARY = [
    {"keys": ["react", "reasoning", "acting", "architecture", "agent pattern", "agent architecture"], "title": "ReAct (arXiv:2210.03629)", "url": "https://arxiv.org/abs/2210.03629", "snippet": "Thought-action-observation agent loop"},
    {"keys": ["plan", "execute", "planner", "architecture", "agent"], "title": "LangChain agent executor", "url": "https://python.langchain.com/docs/how_to/agent_executor/", "snippet": "Plan/execute style agents"},
    {"keys": ["multi-agent", "multi agent", "orchestrat", "supervisor", "architecture"], "title": "AutoGen multi-agent", "url": "https://microsoft.github.io/autogen/", "snippet": "Multi-agent orchestration"},
    {"keys": ["multi-agent", "crew", "architecture"], "title": "CrewAI docs", "url": "https://docs.crewai.com/", "snippet": "Role-based crews"},
    {"keys": ["langgraph", "graph", "architecture", "state"], "title": "LangGraph overview", "url": "https://docs.langchain.com/oss/python/langgraph/overview", "snippet": "Graph orchestration"},
    {"keys": ["architecture", "agent pattern", "tool", "agent architecture"], "title": "Anthropic: Building effective agents", "url": "https://www.anthropic.com/engineering/building-effective-agents", "snippet": "Practical agent patterns"},
]

def _sanitize(q: str) -> str:
    q = re.sub(r"[()\[\]{}]", " ", q or "")
    return re.sub(r"\s+", " ", q).strip()[:120]

def _pattern_hits(query: str) -> list:
    q = (query or "").lower()
    agent_signals = ("agent architecture", "react", "multi-agent", "langgraph", "crewai", "autogen", "planner", "tool-use", "tool use", "agent pattern")
    if not any(s in q for s in agent_signals):
        return []
    return [{"title": i["title"], "url": i["url"], "snippet": i["snippet"], "source": "pattern_library", "query": query} for i in PATTERN_LIBRARY if any(k in q for k in i["keys"])]

def _registry_hits(query: str) -> list:
    q = query.lower(); hits = []
    for key, entries in OFFICIAL_DOCS.items():
        if key in q:
            for e in entries:
                hits.append({"title": e["title"], "url": e["url"], "snippet": e["blurb"], "source": "official_registry", "query": query})
    return hits

def _wikipedia_search(query: str, max_results: int = 5) -> list:
    results = []
    try:
        with httpx.Client(timeout=12) as c:
            r = c.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": query[:200], "srlimit": max_results, "format": "json"}, headers=WIKI_HEADERS)
            if r.status_code != 200:
                return results
            for hit in r.json().get("query", {}).get("search", [])[:max_results]:
                title = hit.get("title") or ""
                snippet = re.sub(r"<[^>]+>", "", hit.get("snippet") or "")
                url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
                results.append({"title": title, "url": url, "snippet": snippet[:220], "source": "wikipedia", "query": query})
            if results:
                slug = results[0]["title"].replace(" ", "_")
                try:
                    sr = c.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}", headers=WIKI_HEADERS)
                    if sr.status_code == 200:
                        d = sr.json()
                        results[0]["snippet"] = (d.get("extract") or results[0]["snippet"])[:400]
                        if d.get("description"):
                            results[0]["title"] = f"{results[0]['title']} — {d.get('description')}"
                except Exception:
                    pass
    except Exception:
        pass
    return results

def _github_search(query: str, max_results: int = 5) -> list:
    results = []
    try:
        with httpx.Client(timeout=12) as c:
            r = c.get("https://api.github.com/search/repositories", params={"q": query[:100], "sort": "stars", "per_page": max_results}, headers={**HEADERS, "Accept": "application/vnd.github+json"})
            if r.status_code == 200:
                for item in r.json().get("items", [])[:max_results]:
                    results.append({"title": f"{item.get('full_name')} ⭐{item.get('stargazers_count', 0)}", "url": item.get("html_url"), "snippet": (item.get("description") or "")[:180], "source": "github", "query": query})
    except Exception:
        pass
    return results

def _hn_search(query: str, max_results: int = 5) -> list:
    results = []
    try:
        with httpx.Client(timeout=12) as c:
            r = c.get("https://hn.algolia.com/api/v1/search", params={"query": query[:100], "tags": "story", "hitsPerPage": max_results}, headers=HEADERS)
            if r.status_code == 200:
                for h in r.json().get("hits", [])[:max_results]:
                    url = h.get("url") or (f"https://news.ycombinator.com/item?id={h.get('objectID')}" if h.get("objectID") else None)
                    if url:
                        results.append({"title": h.get("title") or "HN", "url": url, "snippet": f"pts={h.get('points')}", "source": "hackernews", "query": query})
    except Exception:
        pass
    return results

def web_search(query: str, max_results: int = 8):
    max_results = max(1, min(int(max_results or 8), 10))
    results, q = [], _sanitize(query)
    short = " ".join(q.split()[:8]) or q
    def add(items):
        for h in items or []:
            if h.get("url") and not any(r.get("url") == h["url"] for r in results):
                results.append(h)
    add(_pattern_hits(query)); add(_pattern_hits(q)); add(_registry_hits(q))
    add(_wikipedia_search(q, 5)); add(_wikipedia_search(short, 5))
    for fn, arg in [(_github_search, short), (_hn_search, short)]:
        try:
            add(fn(arg, 5))
        except Exception:
            pass
        if len(results) >= max_results:
            break
    if not results:
        raise RuntimeError("No search results")
    results.sort(key=lambda h: -{"pattern_library": 95, "official_registry": 100, "wikipedia": 85, "github": 50, "hackernews": 40}.get(h.get("source") or "", 0))
    return results[:max_results]

def resolve_official_docs(names: str):
    parts = [p.strip() for p in re.split(r"[,;/]| and ", names) if p.strip()]; found = {}
    for part in parts:
        key = part.lower().replace(" ", "").replace("-", ""); found[part] = []
        for k, entries in OFFICIAL_DOCS.items():
            if k in key or key in k or k in part.lower():
                found[part] = entries; break
    return {"resolved": found}

def fetch_webpage(url: str, max_chars: int = 3000):
    with httpx.Client(timeout=20, follow_redirects=True) as c:
        r = c.get(url, headers=HTML_HEADERS); r.raise_for_status(); soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]): tag.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else "") or url
    text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", soup.get_text(separator="\n")).strip())
    if len(text) > max_chars: text = text[:max_chars] + "\n…[truncated]"
    return {"url": url, "title": title, "content": text, "chars": len(text)}

def research_swarm(topic: str, max_scouts: int = 4, max_readers: int = 3):
    max_scouts = max(2, min(int(max_scouts or 4), 5)); max_readers = max(1, min(int(max_readers or 3), 4))
    topic = (topic or "").strip()
    if not topic: raise ValueError("topic required")
    base = _sanitize(topic)[:100]
    scout_queries = [base, f"{base} wikipedia", f"{base} biography OR profile", f"{base} facts"][:max_scouts]
    bot_log, all_hits = [], []
    def scout(q):
        try:
            hits = web_search(q, max_results=6)
            return {"bot": "scout", "query": q, "ok": True, "count": len(hits), "sources": list({h.get("source") for h in hits}), "hits": hits}
        except Exception as e:
            return {"bot": "scout", "query": q, "ok": False, "error": str(e), "hits": []}
    with ThreadPoolExecutor(max_workers=max_scouts) as pool:
        for fut in as_completed([pool.submit(scout, q) for q in scout_queries]):
            rep = fut.result(); bot_log.append({k: v for k, v in rep.items() if k != "hits"}); all_hits.extend(rep.get("hits") or [])
    seen, top = set(), []
    for h in all_hits:
        u = (h.get("url") or "").rstrip("/")
        if u and u not in seen: seen.add(u); top.append(h)
    top = top[:8]; pages = []; read_urls = [h["url"] for h in top if h.get("url")][:max_readers]
    def reader(url):
        try:
            page = fetch_webpage(url, max_chars=2500)
            return {"bot": "reader", "url": url, "ok": True, "title": page.get("title"), "page": page}
        except Exception as e:
            return {"bot": "reader", "url": url, "ok": False, "error": str(e)}
    with ThreadPoolExecutor(max_workers=max_readers) as pool:
        for fut in as_completed([pool.submit(reader, u) for u in read_urls]):
            rep = fut.result(); bot_log.append({k: v for k, v in rep.items() if k != "page"})
            if rep.get("ok") and rep.get("page"): pages.append(rep["page"])
    return {"topic": topic, "scouts": len(scout_queries), "readers": len(read_urls), "hits": [{"title": h.get("title"), "url": h.get("url"), "source": h.get("source"), "snippet": (h.get("snippet") or "")[:200]} for h in top], "pages": pages, "bot_log": bot_log, "policy": "public_web_only"}

TOOLS = {
    "research_swarm": {"schema": {"type": "function", "function": {"name": "research_swarm", "description": "Parallel research bots. Uses Wikipedia + GitHub + HN. Topic-only scouts.", "parameters": {"type": "object", "properties": {"topic": {"type": "string"}, "max_scouts": {"type": "integer", "default": 4}, "max_readers": {"type": "integer", "default": 3}}, "required": ["topic"]}}}, "fn": research_swarm},
    "web_search": {"schema": {"type": "function", "function": {"name": "web_search", "description": "Wikipedia + GitHub + HN + pattern library (agents only) + docs.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 8}}, "required": ["query"]}}}, "fn": web_search},
    "resolve_official_docs": {"schema": {"type": "function", "function": {"name": "resolve_official_docs", "description": "Official product URLs.", "parameters": {"type": "object", "properties": {"names": {"type": "string"}}, "required": ["names"]}}}, "fn": resolve_official_docs},
    "fetch_webpage": {"schema": {"type": "function", "function": {"name": "fetch_webpage", "description": "Fetch public page text.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer", "default": 3000}}, "required": ["url"]}}}, "fn": fetch_webpage},
}
def tool_schemas(): return [t["schema"] for t in TOOLS.values()]
def run_tool(name, args):
    e = TOOLS.get(name)
    if not e: return {"ok": False, "error": f"Unknown: {name}"}
    try: return {"ok": True, "output": e["fn"](**(args or {}))}
    except Exception as ex: return {"ok": False, "error": str(ex)}

def groq_chat(messages, tools=None, max_tokens=900, tool_choice="auto"):
    from groq import Groq
    key = os.environ.get("GROQ_API_KEY")
    if not key: raise ValueError("GROQ_API_KEY not set")
    client = Groq(api_key=key); model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    kwargs = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    if tools: kwargs["tools"] = tools; kwargs["tool_choice"] = tool_choice
    last = None
    for m in [model] + [x for x in FALLBACK_MODELS if x != model]:
        try:
            kwargs["model"] = m; completion = client.chat.completions.create(**kwargs); msg = completion.choices[0].message; tcs = []
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    try: args = json.loads(tc.function.arguments or "{}")
                    except Exception: args = {}
                    tcs.append({"id": tc.id or str(uuid.uuid4()), "name": tc.function.name, "arguments": args})
            usage = {}
            if completion.usage: usage = {"prompt_tokens": completion.usage.prompt_tokens or 0, "completion_tokens": completion.usage.completion_tokens or 0, "total_tokens": completion.usage.total_tokens or 0}
            return {"content": msg.content, "tool_calls": tcs, "usage": usage, "model": m}
        except Exception as e:
            last = e; es = str(e).lower()
            if "rate" in es or "429" in es: time.sleep(1.5); continue
            if "model" in es and ("not found" in es or "does not exist" in es): continue
            raise
    raise last or RuntimeError("Groq failed")

SYSTEM = "You are Angvey Agent OS. Prefer research_swarm or web_search. Cite title+URL from tool evidence only. Public web only. After evidence, stop tools and answer. Do not invent sources."

def run_agent(goal, max_iters=6, verify=True):
    task_id = str(uuid.uuid4()); phases, events, tlog, evidence_chunks = [], [], [], []
    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}; model_used, ok_tools, draft = None, 0, None
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Goal: {goal}\nPrefer research_swarm. Cite only retrieved sources."}]
    phases += [{"id": "understand", "label": "Understand goal", "status": "done", "detail": goal[:200]}, {"id": "plan", "label": "Plan & execute tools", "status": "running", "detail": ""}]
    for i in range(max_iters):
        events.append({"kind": "iteration", "detail": i + 1})
        force_final = (ok_tools >= 1 and i >= 2) or (i >= max_iters - 1)
        if force_final: messages.append({"role": "user", "content": "STOP tools. Final answer with URLs from evidence only."})
        try:
            resp = groq_chat(messages, tools=None if force_final else tool_schemas(), max_tokens=900, tool_choice="none" if force_final else "auto")
        except Exception as e:
            err = str(e); events.append({"kind": "error", "detail": err[:300]})
            if "429" in err or "rate" in err.lower(): time.sleep(2 + i); continue
            phases[-1]["status"] = "failed"
            return {"task_id": task_id, "status": "failed", "result": f"Model error: {err}", "tool_calls": tlog, "tokens": tokens, "errors": [err[:200]], "model": model_used, "events": events, "phases": phases, "verification": None, "confidence": None, "unique": {}}
        model_used = resp.get("model")
        for k in tokens: tokens[k] += (resp.get("usage") or {}).get(k, 0)
        if resp.get("content"): events.append({"kind": "thought", "detail": (resp["content"] or "")[:350]})
        tcs = resp.get("tool_calls") or []
        if tcs and not force_final:
            messages.append({"role": "assistant", "content": resp.get("content"), "tool_calls": [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments") or {})}} for tc in tcs]})
            for tc in tcs:
                name, args = tc["name"], tc.get("arguments") or {}
                events.append({"kind": "tool_call", "detail": {"name": name, "arguments": args}})
                result = run_tool(name, args); tlog.append({"name": name, "arguments": args, "ok": result.get("ok")})
                if result.get("ok"): ok_tools += 1
                events.append({"kind": "tool_result", "detail": {"name": name, "ok": result.get("ok"), "preview": str(result.get("output") or result.get("error"))[:250]}})
                if name == "research_swarm" and result.get("ok") and isinstance(result.get("output"), dict):
                    for bl in (result["output"].get("bot_log") or [])[:10]: events.append({"kind": "bot", "detail": bl})
                payload = result.get("output") if result.get("ok") else {"error": result.get("error")}
                content = json.dumps(payload, ensure_ascii=False, default=str)
                if result.get("ok"): evidence_chunks.append(content[:3000])
                if len(content) > 4000: content = content[:4000] + "…"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name, "content": content})
            continue
        draft = (resp.get("content") or "").strip() or "Completed."; break
    if not draft:
        if evidence_chunks:
            resp = groq_chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Goal: {goal}\nEvidence:\n" + "\n---\n".join(evidence_chunks[:5]) + "\nAnswer with citations."}], tools=None, max_tokens=900, tool_choice="none")
            for k in tokens: tokens[k] += (resp.get("usage") or {}).get(k, 0)
            model_used = resp.get("model") or model_used; draft = (resp.get("content") or "").strip() or "Partial."
        else:
            phases[-1]["status"] = "failed"
            return {"task_id": task_id, "status": "failed", "result": "No evidence.", "tool_calls": tlog, "tokens": tokens, "errors": ["NO_EVIDENCE"], "model": model_used, "events": events, "phases": phases, "verification": None, "confidence": None, "unique": {}}
    phases[-1]["status"] = "done"; phases[-1]["detail"] = f"{len(tlog)} tools"
    phases.append({"id": "synthesize", "label": "Synthesize answer", "status": "done", "detail": draft[:100]})
    phases.append({"id": "deliver", "label": "Deliver", "status": "done", "detail": "done"})
    return {"task_id": task_id, "status": "completed", "result": draft, "tool_calls": tlog, "tokens": tokens, "errors": [], "model": model_used, "events": events[-40:], "phases": phases, "verification": None, "confidence": 0.75 if evidence_chunks else 0.4, "unique": {"wikipedia": True, "pattern_library": True, "research_swarm": True, "parallel_bots": True, "public_web_only": True}}

class RunRequest(BaseModel):
    goal: str; mock: bool = False; max_iters: int = 6; verify: bool = True

@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "angvey-agent-os", "version": "0.4.3", "has_groq_key": bool(os.environ.get("GROQ_API_KEY")), "default_model": DEFAULT_MODEL, "unique_features": ["wikipedia", "pattern_library", "research_swarm", "parallel_bots"], "tools": list(TOOLS.keys()), "search_backends": ["wikipedia", "pattern_library", "github", "hackernews", "official_registry"]}

@app.get("/api/tools")
@app.get("/tools")
def list_tools(): return {"tools": list(TOOLS.keys())}

@app.post("/api/agent/run")
@app.post("/agent/run")
def agent_run(req: RunRequest):
    if req.mock:
        return {"task_id": str(uuid.uuid4()), "status": "completed", "result": f"[mock] {req.goal[:120]}", "tool_calls": [], "tokens": {}, "errors": [], "model": "mock", "events": [], "phases": [], "verification": None, "confidence": 0.5, "unique": {}}
    return run_agent(req.goal, max_iters=min(req.max_iters, 8), verify=req.verify)

@app.get("/")
@app.get("/api")
def root():
    return {"service": "angvey-agent-os", "version": "0.4.3", "run": "POST /api/agent/run"}
