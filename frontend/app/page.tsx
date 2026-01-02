"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const DEFAULT_API_BASE = "http://localhost:8000";

const promptWithFile = (message: string, fileName: string, fileContent: string) => {
  if (!fileContent.trim()) {
    return message;
  }
  return [
    message,
    "\n\n<FILE>",
    `name: ${fileName || "main.tf"}`,
    fileContent,
    "</FILE>",
  ].join("\n");
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const parseSseEvents = (
  buffer: string,
  onData: (data: string) => void,
  onDone: (payload: string) => void
) => {
  const parts = buffer.split("\n\n");
  const remaining = parts.pop() ?? "";

  for (const part of parts) {
    const lines = part.split("\n");
    let eventName = "message";
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.replace("event:", "").trim();
        continue;
      }
      if (line.startsWith("data:")) {
        dataLines.push(line.slice(5));
      }
    }

    if (!dataLines.length) {
      continue;
    }

    if (eventName === "done") {
      onDone(dataLines.join("\n"));
      continue;
    }

    onData(dataLines.join("\n"));
  }

  return remaining;
};

export default function Home() {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [fileName, setFileName] = useState("main.tf");
  const [fileContent, setFileContent] = useState("");
  const [includeFile, setIncludeFile] = useState(true);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [lastDiff, setLastDiff] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [status, setStatus] = useState("Creating session...");
  const [isStreaming, setIsStreaming] = useState(false);
  const streamBuffer = useRef("");
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  useEffect(() => {
    let isMounted = true;

    const bootstrap = async () => {
      try {
        setStatus("Creating session...");
        const response = await fetch(`${apiBase}/api/session`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error("Failed to create session");
        }
        const data = (await response.json()) as { session_id: string };
        if (isMounted) {
          setSessionId(data.session_id);
          setStatus("Session ready");
        }
      } catch (error) {
        if (isMounted) {
          setStatus("Session error - check API base URL");
        }
      }
    };

    bootstrap();
    return () => {
      isMounted = false;
    };
  }, [apiBase]);

  const canSend = useMemo(() => {
    return Boolean(sessionId) && !isStreaming && input.trim().length > 0;
  }, [sessionId, isStreaming, input]);

  const sendMessage = async () => {
    if (!sessionId || isStreaming) {
      return;
    }

    const messagePayload = includeFile
      ? promptWithFile(input, fileName, fileContent)
      : input;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: input },
      { role: "assistant", content: "" },
    ]);
    setInput("");
    setIsStreaming(true);
    streamBuffer.current = "";

    try {
      const response = await fetch(`${apiBase}/api/message/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: messagePayload,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("Streaming request failed");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        streamBuffer.current += decoder.decode(value, { stream: true });
        streamBuffer.current = parseSseEvents(
          streamBuffer.current,
          (chunk) => {
            setMessages((prev) => {
              const next = [...prev];
              const lastIndex = next.length - 1;
              if (lastIndex >= 0 && next[lastIndex].role === "assistant") {
                next[lastIndex] = {
                  ...next[lastIndex],
                  content: next[lastIndex].content + chunk,
                };
              }
              return next;
            });
          },
          (payload) => {
            try {
              const data = JSON.parse(payload) as { diff?: string | null };
              if (data.diff) {
                setLastDiff(data.diff);
              }
            } catch {
              // ignore parse failures
            }
          }
        );
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          role: "assistant",
          content: "Streaming failed. Check the API server and try again.",
        },
      ]);
    } finally {
      setIsStreaming(false);
    }
  };

  const approvePatch = async (approved: boolean) => {
    if (!sessionId) {
      return;
    }
    setIsStreaming(true);
    try {
      const response = await fetch(`${apiBase}/api/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          approved,
          reason: approved ? null : rejectionReason || "No reason provided.",
        }),
      });
      if (!response.ok) {
        throw new Error("Approval request failed");
      }
      const data = (await response.json()) as { text: string; diff?: string | null };
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.text,
        },
      ]);
      if (data.diff) {
        setLastDiff(data.diff);
      }
      setRejectionReason("");
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Approval request failed. Check the API server.",
        },
      ]);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_#f8efe2,_#f4f7f5_50%,_#f7f0e8_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-10">
        <header className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Sentinel-RAG
              </p>
              <h1 className="text-4xl font-semibold tracking-tight text-slate-900">
                IaC Autofix Studio
              </h1>
            </div>
            <div className="rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-xs font-medium uppercase tracking-[0.2em] text-slate-600">
              {status}
            </div>
          </div>
          <p className="max-w-2xl text-base text-slate-600">
            Paste IaC, discuss issues, and apply targeted diffs only after approval.
            This is a local session backed by the Sentinel-RAG agent.
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-[1.1fr_1.5fr]">
          <div className="rounded-3xl border border-slate-200/80 bg-white/90 p-6 shadow-[0_20px_60px_-40px_rgba(15,23,42,0.35)]">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900">IaC Input</h2>
              <label className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-slate-500">
                <input
                  type="checkbox"
                  checked={includeFile}
                  onChange={(event) => setIncludeFile(event.target.checked)}
                />
                include
              </label>
            </div>
            <div className="mt-4">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                File name
              </label>
              <input
                className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
                value={fileName}
                onChange={(event) => setFileName(event.target.value)}
              />
            </div>
            <div className="mt-4">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                File contents
              </label>
              <textarea
                className="mt-2 h-64 w-full rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-mono text-slate-700"
                value={fileContent}
                onChange={(event) => setFileContent(event.target.value)}
                placeholder="Paste Terraform, CloudFormation, or K8s manifests here."
              />
            </div>
            <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
              Session ID: {sessionId ?? "pending"}
              <br />
              API Base: {apiBase}
            </div>
          </div>

          <div className="flex flex-col rounded-3xl border border-slate-200/80 bg-white/90 p-6 shadow-[0_20px_60px_-40px_rgba(15,23,42,0.35)]">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900">Conversation</h2>
              <input
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500"
                value={apiBase}
                onChange={(event) => setApiBase(event.target.value)}
              />
            </div>
            <div className="mt-4 flex h-[420px] flex-col gap-4 overflow-y-auto rounded-2xl bg-gradient-to-b from-white to-slate-50 p-4">
              {messages.length === 0 ? (
                <div className="text-sm text-slate-500">
                  Ask the agent to review or propose a fix. Example: "Read main.tf
                  and propose a minimal diff to fix insecure settings."
                </div>
              ) : (
                messages.map((message, index) => (
                  <div
                    key={`${message.role}-${index}`}
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                      message.role === "user"
                        ? "ml-auto bg-slate-900 text-white"
                        : "bg-white text-slate-800"
                    }`}
                  >
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                        code: ({ children }) => (
                          <code className="rounded bg-slate-100 px-1 py-0.5 text-xs text-slate-800">
                            {children}
                          </code>
                        ),
                        pre: ({ children }) => (
                          <pre className="mt-2 overflow-auto rounded-xl bg-slate-900 p-3 text-xs text-slate-100">
                            {children}
                          </pre>
                        ),
                        ul: ({ children }) => (
                          <ul className="ml-4 list-disc space-y-1">{children}</ul>
                        ),
                        ol: ({ children }) => (
                          <ol className="ml-4 list-decimal space-y-1">{children}</ol>
                        ),
                        a: ({ children, href }) => (
                          <a className="text-emerald-600 underline" href={href}>
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                ))
              )}
              {isStreaming && (
                <div className="max-w-[85%] rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
                  Streaming response...
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <div className="mt-4 flex flex-col gap-3">
              <textarea
                className="h-28 w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask for findings, propose fixes, or request a diff."
              />
              <div className="flex flex-wrap gap-3">
                <button
                  className={`rounded-2xl px-4 py-3 text-sm font-semibold uppercase tracking-[0.2em] transition ${
                    canSend
                      ? "bg-slate-900 text-white hover:bg-slate-800"
                      : "cursor-not-allowed bg-slate-200 text-slate-400"
                  }`}
                  onClick={sendMessage}
                  disabled={!canSend}
                >
                  {isStreaming ? "Streaming..." : "Send"}
                </button>
                <button
                  className={`rounded-2xl border border-emerald-200 px-4 py-3 text-xs font-semibold uppercase tracking-[0.2em] transition ${
                    lastDiff && !isStreaming
                      ? "bg-emerald-600 text-white hover:bg-emerald-500"
                      : "cursor-not-allowed bg-emerald-50 text-emerald-300"
                  }`}
                  onClick={() => approvePatch(true)}
                  disabled={!lastDiff || isStreaming}
                >
                  Approve
                </button>
                <button
                  className={`rounded-2xl border border-rose-200 px-4 py-3 text-xs font-semibold uppercase tracking-[0.2em] transition ${
                    lastDiff && !isStreaming
                      ? "bg-rose-500 text-white hover:bg-rose-400"
                      : "cursor-not-allowed bg-rose-50 text-rose-300"
                  }`}
                  onClick={() => approvePatch(false)}
                  disabled={!lastDiff || isStreaming}
                >
                  Reject
                </button>
              </div>
              <input
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500"
                value={rejectionReason}
                onChange={(event) => setRejectionReason(event.target.value)}
                placeholder="Rejection reason (optional)"
              />
            </div>
          </div>
        </section>
        {lastDiff && (
          <section className="rounded-3xl border border-slate-200/80 bg-white/90 p-6 shadow-[0_20px_60px_-40px_rgba(15,23,42,0.35)]">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900">Latest Diff</h2>
              <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                pending approval
              </span>
            </div>
            <pre className="mt-4 max-h-80 overflow-auto rounded-2xl bg-slate-900 p-4 text-xs text-emerald-100">
              {lastDiff}
            </pre>
          </section>
        )}
      </div>
    </div>
  );
}
