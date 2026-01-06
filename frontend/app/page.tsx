"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { ComponentPropsWithoutRef } from "react";
import remarkGfm from "remark-gfm";
import { DiffViewer, isDiffData } from "./components/DiffViewer";
import { VscodeCodeEditor, VscodeDiffViewer } from "./components/VscodeEditor";

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "tool" | "reasoning";
  content: string;
  toolName?: string;
  toolCallId?: string;
  toolArgs?: string;
  toolOutput?: string;
  toolStatus?: "running" | "done";
};

type FileDiff = {
  filePath: string;
  oldContent: string;
  newContent: string;
  operationType: "create_file" | "update_file" | "delete_file";
};

type FileNode = {
  name: string;
  path: string;
  is_dir: boolean;
  children?: FileNode[] | null;
};

const uid = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

type MarkdownCodeProps = ComponentPropsWithoutRef<"code"> & { inline?: boolean };

const Markdown = ({ content }: { content: string }) => (
  <div className="text-[13px] leading-relaxed text-[#d4d4d4]">
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="my-2">{children}</p>,
        h1: ({ children }) => <h1 className="my-3 text-lg font-semibold">{children}</h1>,
        h2: ({ children }) => <h2 className="my-3 text-base font-semibold">{children}</h2>,
        h3: ({ children }) => <h3 className="my-2 text-sm font-semibold">{children}</h3>,
        ul: ({ children }) => <ul className="my-2 list-disc pl-5">{children}</ul>,
        ol: ({ children }) => <ol className="my-2 list-decimal pl-5">{children}</ol>,
        li: ({ children }) => <li className="my-1">{children}</li>,
        a: ({ children, href }) => (
          <a
            className="text-[#4fc1ff] underline underline-offset-2"
            href={href}
            target="_blank"
            rel="noreferrer"
          >
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-[#3c3c3c] pl-3 text-[#9da1a6]">
            {children}
          </blockquote>
        ),
        code: ({ children, inline, ...rest }: MarkdownCodeProps) =>
          inline ? (
            <code className="rounded bg-[#1e1e1e] px-1 py-0.5 font-mono text-[12px] text-[#dcdcaa]">
              {children}
            </code>
          ) : (
            <code className="font-mono text-[12px] text-[#d4d4d4]" {...rest}>
              {children}
            </code>
          ),
        pre: ({ children }) => (
          <pre className="my-2 max-h-80 overflow-auto rounded border border-[#3c3c3c] bg-[#1e1e1e] p-3 font-mono text-[12px] text-[#d4d4d4]">
            {children}
          </pre>
        ),
        table: ({ children }) => (
          <div className="my-2 overflow-auto rounded border border-[#3c3c3c]">
            <table className="w-full border-collapse text-[12px]">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border-b border-[#3c3c3c] bg-[#1e1e1e] p-2 text-left font-semibold">
            {children}
          </th>
        ),
        td: ({ children }) => <td className="border-b border-[#2d2d2d] p-2 align-top">{children}</td>,
      }}
    >
      {content}
    </ReactMarkdown>
  </div>
);

// Resizable divider component
const ResizeDivider = ({
  onDrag,
  direction,
}: {
  onDrag: (delta: number) => void;
  direction: "left" | "right";
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const startX = useRef(0);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - startX.current;
      startX.current = e.clientX;
      onDrag(direction === "left" ? delta : -delta);
    };

    const handleMouseUp = () => setIsDragging(false);

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging, onDrag, direction]);

  return (
    <div
      onMouseDown={(e) => {
        startX.current = e.clientX;
        setIsDragging(true);
      }}
      className={`w-1 cursor-col-resize hover:bg-[#007acc] transition-colors ${
        isDragging ? "bg-[#007acc]" : "bg-transparent"
      }`}
    />
  );
};

// Debounce hook for auto-sync
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

// SSE parser
const parseSseEvents = (
  buffer: string,
  handlers: {
    onText: (text: string) => void;
    onToolCall: (payload: { name: string; args: string; callId?: string }) => void;
    onToolOutput: (payload: { output: string; callId?: string }) => void;
    onReasoning: (summary: string) => void;
    onDone: (payload?: { final_output?: string; last_response_id?: string }) => void;
  }
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
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5));
      }
    }

    if (!dataLines.length) continue;
    const data = dataLines.join("\n");

    if (eventName === "done") {
      try {
        handlers.onDone(JSON.parse(data));
      } catch {
        handlers.onDone();
      }
    } else if (eventName === "tool_called") {
      try {
        const payload = JSON.parse(data);
        handlers.onToolCall({
          name: payload.name || "tool",
          args: payload.arguments || "",
          callId: payload.call_id || undefined,
        });
      } catch {}
    } else if (eventName === "tool_output") {
      try {
        const payload = JSON.parse(data);
        const output = typeof payload.output === "string"
          ? payload.output
          : JSON.stringify(payload.output, null, 2);
        handlers.onToolOutput({
          output,
          callId: payload.call_id || undefined,
        });
      } catch {}
    } else if (eventName === "reasoning") {
      try {
        const payload = JSON.parse(data);
        if (payload.summary) {
          handlers.onReasoning(payload.summary);
        }
      } catch {}
    } else {
      handlers.onText(data);
    }
  }

  return remaining;
};

// File tree component
const FileTree = ({
  nodes,
  selectedPath,
  onSelect,
  depth = 0,
}: {
  nodes: FileNode[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
  depth?: number;
}) => {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  return (
    <div className="text-xs">
      {nodes.map((node) => (
        <div key={node.path}>
          <button
            onClick={() => {
              if (node.is_dir) {
	                setExpanded((prev) => {
	                  const next = new Set(prev);
	                  if (next.has(node.path)) {
	                    next.delete(node.path);
	                  } else {
	                    next.add(node.path);
	                  }
	                  return next;
	                });
	              } else {
	                onSelect(node.path);
              }
            }}
            className={`flex w-full items-center gap-1.5 px-2 py-1 text-left hover:bg-[#2a2a2a] ${
              selectedPath === node.path ? "bg-[#094771]" : ""
            }`}
            style={{ paddingLeft: `${depth * 12 + 8}px` }}
          >
            <span className="text-[#9da1a6] text-[10px]">
              {node.is_dir ? (expanded.has(node.path) ? "▼" : "▶") : "·"}
            </span>
            <span className={node.is_dir ? "text-[#dcdc9d]" : "text-[#d4d4d4]"}>
              {node.name}
            </span>
          </button>
          {node.is_dir && node.children && expanded.has(node.path) && (
            <FileTree nodes={node.children} selectedPath={selectedPath} onSelect={onSelect} depth={depth + 1} />
          )}
        </div>
      ))}
    </div>
  );
};

// Test files
const TEST_FILES: Record<string, { name: string; content: string }> = {
  s3: {
    name: "s3_bucket.tf",
    content: `resource "aws_s3_bucket" "data" {
  bucket = "my-data-bucket"
}

resource "aws_s3_bucket_acl" "data" {
  bucket = aws_s3_bucket.data.id
  acl    = "public-read"
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}
`,
  },
  sg: {
    name: "security_group.tf",
    content: `resource "aws_security_group" "web" {
  name        = "web-sg"
  description = "Allow web traffic"
  vpc_id      = var.vpc_id

  ingress {
    description = "SSH from anywhere"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
`,
  },
  rds: {
    name: "rds.tf",
    content: `resource "aws_db_instance" "main" {
  identifier           = "main-db"
  allocated_storage    = 20
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = "db.t3.micro"
  db_name              = "mydb"
  username             = "admin"
  password             = "password123"
  skip_final_snapshot  = true
  publicly_accessible  = true
  storage_encrypted    = false
}
`,
  },
};

export default function Home() {
  const [apiBase] = useState(DEFAULT_API_BASE);
  const [status, setStatus] = useState("Connecting...");
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Pane widths (resizable)
  const [leftPaneWidth, setLeftPaneWidth] = useState(240);
  const [rightPaneWidth, setRightPaneWidth] = useState(300);

  // File state
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [newFileName, setNewFileName] = useState("");
  const [showNewFile, setShowNewFile] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  // Active diff state for file viewer
  const [activeDiff, setActiveDiff] = useState<FileDiff | null>(null);
  const [lastDiffByPath, setLastDiffByPath] = useState<Record<string, FileDiff>>({});
  const [lastDiff, setLastDiff] = useState<FileDiff | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const streamBuffer = useRef("");
  const lastSyncedContent = useRef("");
  const toolMessageIdsByCallId = useRef<Map<string, string>>(new Map());
  const toolNamesByCallId = useRef<Map<string, string>>(new Map());

  // Resize handlers
  const handleLeftResize = useCallback((delta: number) => {
    setLeftPaneWidth((w) => Math.max(160, Math.min(400, w + delta)));
  }, []);

  const handleRightResize = useCallback((delta: number) => {
    setRightPaneWidth((w) => Math.max(240, Math.min(460, w + delta)));
  }, []);

  // Auto-sync
  const debouncedContent = useDebounce(fileContent, 800);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: isStreaming ? "auto" : "smooth" });
  }, [messages, isStreaming]);

  // Refresh file tree
  const refreshFiles = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`${apiBase}/api/file/list`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (res.ok) {
        const data = await res.json();
        setFileTree(data.files ?? []);
      }
    } catch {}
  }, [apiBase, sessionId]);

  // Save file
  const saveFile = useCallback(
    async (path: string, content: string) => {
      if (!sessionId) return;
      try {
        await fetch(`${apiBase}/api/file/upsert`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, path, content }),
        });
        lastSyncedContent.current = content;
        await refreshFiles();
      } catch {}
    },
    [apiBase, sessionId, refreshFiles]
  );

  // Auto-sync effect
  useEffect(() => {
    if (!selectedFile || !sessionId) return;
    if (debouncedContent === lastSyncedContent.current) return;
    saveFile(selectedFile, debouncedContent);
  }, [debouncedContent, selectedFile, sessionId, saveFile]);

  // Read file
  const readFile = useCallback(
    async (path: string) => {
      if (!sessionId) return;
      try {
        const res = await fetch(`${apiBase}/api/file/read`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, path }),
        });
        if (res.ok) {
          const data = await res.json();
          setFileContent(data.content);
          lastSyncedContent.current = data.content;
        }
      } catch {}
    },
    [apiBase, sessionId]
  );

  // Select file
  const selectFile = useCallback(
    async (path: string) => {
      if (selectedFile && fileContent !== lastSyncedContent.current) {
        await saveFile(selectedFile, fileContent);
      }
      setSelectedFile(path);
      await readFile(path);
    },
    [selectedFile, fileContent, saveFile, readFile]
  );

  // Create file
  const createFile = async () => {
    if (!newFileName.trim() || !sessionId) return;
    await saveFile(newFileName.trim(), "");
    setSelectedFile(newFileName.trim());
    setFileContent("");
    lastSyncedContent.current = "";
    setShowNewFile(false);
    setNewFileName("");
  };

  // Load test file
  const loadTestFile = async (key: string) => {
    const tf = TEST_FILES[key];
    if (!tf || !sessionId) return;
    await saveFile(tf.name, tf.content);
    setSelectedFile(tf.name);
    setFileContent(tf.content);
    lastSyncedContent.current = tf.content;
  };

  // Send chat message
  const sendMessage = async () => {
    if (!sessionId || isStreaming || !input.trim()) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { id: uid(), role: "user", content: userMessage }]);
    setIsStreaming(true);
    streamBuffer.current = "";

    toolMessageIdsByCallId.current = new Map();
    toolNamesByCallId.current = new Map();

    // Create a streaming message ID to update in real-time
    const streamingMessageId = uid();

    try {
      const res = await fetch(`${apiBase}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: userMessage }),
      });

      if (!res.ok || !res.body) throw new Error("Stream failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let donePayload: { final_output?: string; last_response_id?: string } | undefined;
      let gotDoneEvent = false;
      let fullText = "";
      let hasAddedStreamingMessage = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        streamBuffer.current += decoder.decode(value, { stream: true });
        streamBuffer.current = parseSseEvents(streamBuffer.current, {
          onText: (text) => {
            fullText += text;
            // Add streaming message on first text chunk
            if (!hasAddedStreamingMessage) {
              hasAddedStreamingMessage = true;
              setMessages((prev) => [
                ...prev,
                { id: streamingMessageId, role: "assistant", content: fullText },
              ]);
            } else {
              // Update the streaming message content in real-time
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === streamingMessageId ? { ...m, content: fullText } : m
                )
              );
            }
          },
          onToolCall: ({ name, args, callId }) => {
            const id = uid();
            const key = callId || id;
            toolMessageIdsByCallId.current.set(key, id);
            toolNamesByCallId.current.set(key, name);
            setMessages((prev) => [
              ...prev,
              {
                id,
                role: "tool",
                content: "",
                toolName: name,
                toolCallId: callId,
                toolArgs: args,
                toolStatus: "running",
              },
            ]);
          },
          onToolOutput: ({ output, callId }) => {
            const key = callId;
            const existingId = key ? toolMessageIdsByCallId.current.get(key) : undefined;
            const toolName = key ? toolNamesByCallId.current.get(key) : undefined;

            // Check if this is an apply_patch output with diff data
            if (toolName === "apply_patch") {
              const diffData = isDiffData(output);
              if (diffData) {
                const diff: FileDiff = {
                  filePath: diffData.file_path,
                  oldContent: diffData.old_content,
                  newContent: diffData.new_content,
                  operationType: diffData.operation_type,
                };
                setActiveDiff(diff);
                setLastDiffByPath((prev) => ({ ...prev, [diff.filePath]: diff }));
                setLastDiff(diff);
                // Auto-select the file that was modified
                setSelectedFile(diffData.file_path);
              }
            }

            if (!existingId) {
              setMessages((prev) => [
                ...prev,
                {
                  id: uid(),
                  role: "tool",
                  content: "",
                  toolName: toolName || "tool_output",
                  toolCallId: callId,
                  toolOutput: output,
                  toolStatus: "done",
                },
              ]);
              return;
            }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === existingId
                  ? {
                      ...m,
                      toolOutput: output,
                      toolStatus: "done",
                    }
                  : m
              )
            );
          },
          onReasoning: (summary) => {
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "reasoning", content: summary },
            ]);
          },
          onDone: (payload) => {
            gotDoneEvent = true;
            donePayload = payload;
          },
        });
      }

      const finalText = gotDoneEvent && donePayload?.final_output ? donePayload.final_output : fullText;

      // Update existing streaming message or add new one if no text was streamed
      if (hasAddedStreamingMessage) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === streamingMessageId ? { ...m, content: finalText || "[No response]" } : m
          )
        );
      } else {
        setMessages((prev) => [...prev, { id: uid(), role: "assistant", content: finalText || "[No response]" }]);
      }

      // Refresh files after agent might have modified them
      await refreshFiles();
      if (selectedFile) await readFile(selectedFile);
    } catch {
      setMessages((prev) => [...prev, { id: uid(), role: "assistant", content: "[Error: Connection failed]" }]);
    } finally {
      setIsStreaming(false);
    }
  };

  // Bootstrap
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setStatus("Creating session...");
        const res = await fetch(`${apiBase}/api/session`, { method: "POST" });
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!mounted) return;
        setSessionId(data.session_id);
        setStatus("Ready");

        // Add welcome message
        setMessages([{
          id: uid(),
          role: "assistant",
          content: "Hi! I'm Sentinel-RAG, your IaC security assistant. Load a test file or create your own, then ask me to scan and fix security issues. Just say something like \"scan my terraform files\" to get started!"
        }]);
      } catch {
        if (mounted) setStatus("Connection failed");
      }
    })();
    return () => { mounted = false; };
  }, [apiBase]);

  useEffect(() => {
    if (sessionId) refreshFiles();
  }, [sessionId, refreshFiles]);

  return (
    <div className="flex h-screen bg-[#1e1e1e] text-[#d4d4d4]">
      {/* Left sidebar - Files */}
      <aside
        className="flex flex-col border-r border-[#2d2d2d] bg-[#252526]"
        style={{ width: leftPaneWidth, minWidth: leftPaneWidth }}
      >
        <div className="border-b border-[#2d2d2d] p-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#9da1a6]">
              Files
            </span>
            <button
              onClick={() => setShowNewFile(true)}
              className="rounded px-2 py-0.5 text-xs text-[#9da1a6] hover:bg-[#3c3c3c] hover:text-white"
            >
              + New
            </button>
          </div>

          {showNewFile && (
            <div className="mt-2 flex gap-1">
              <input
                className="flex-1 rounded border border-[#3c3c3c] bg-[#1e1e1e] px-2 py-1 text-xs"
                placeholder="filename.tf"
                value={newFileName}
                onChange={(e) => setNewFileName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && createFile()}
                autoFocus
              />
              <button onClick={createFile} className="rounded bg-[#007acc] px-2 text-xs text-white">
                OK
              </button>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-auto">
          {fileTree.length === 0 ? (
            <div className="p-3 text-xs text-[#9da1a6]">No files yet</div>
          ) : (
            <FileTree nodes={fileTree} selectedPath={selectedFile} onSelect={selectFile} />
          )}
        </div>

        <div className="border-t border-[#2d2d2d] p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#9da1a6] mb-2">
            Test Files
          </div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(TEST_FILES).map(([key, file]) => (
              <button
                key={key}
                onClick={() => loadTestFile(key)}
                className="rounded border border-[#3c3c3c] bg-[#1e1e1e] px-2 py-1 text-[10px] text-[#9da1a6] hover:bg-[#2a2a2a] hover:text-white"
              >
                {file.name}
              </button>
            ))}
          </div>
        </div>
      </aside>

      {/* Left resize divider */}
      <ResizeDivider onDrag={handleLeftResize} direction="left" />

      {/* Center - Editor */}
      <main className="flex flex-1 flex-col min-w-0">
        <div className="flex h-9 items-center justify-between border-b border-[#2d2d2d] bg-[#252526] px-4">
          <div className="flex items-center gap-2">
            {selectedFile ? (
              <span className="text-xs text-[#d4d4d4]">{selectedFile}</span>
            ) : (
              <span className="text-xs text-[#9da1a6]">No file selected</span>
            )}
            {activeDiff && activeDiff.filePath === selectedFile && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1f6feb]/30 text-[#58a6ff]">
                Diff View
              </span>
            )}
          </div>
          {activeDiff && activeDiff.filePath === selectedFile ? (
            <button
              onClick={() => {
                setActiveDiff(null);
                // Reload file content to show the new state
                if (selectedFile) readFile(selectedFile);
              }}
              className="text-[10px] px-2 py-1 rounded bg-[#238636] text-white hover:bg-[#2ea043]"
            >
              Accept & Close
            </button>
          ) : selectedFile && lastDiffByPath[selectedFile] ? (
            <button
              onClick={() => setActiveDiff(lastDiffByPath[selectedFile])}
              className="text-[10px] px-2 py-1 rounded border border-[#3c3c3c] bg-[#1e1e1e] text-[#d4d4d4] hover:bg-[#2a2a2a]"
              title="View the last changes applied by the agent"
            >
              View Changes
            </button>
          ) : lastDiff ? (
            <button
              onClick={() => {
                setSelectedFile(lastDiff.filePath);
                setActiveDiff(lastDiff);
              }}
              className="text-[10px] px-2 py-1 rounded border border-[#3c3c3c] bg-[#1e1e1e] text-[#d4d4d4] hover:bg-[#2a2a2a]"
              title="View the most recent diff from the agent"
            >
              View Last Change
            </button>
          ) : null}
        </div>
        <div className="flex-1 overflow-hidden">
          {activeDiff && activeDiff.filePath === selectedFile ? (
            <VscodeDiffViewer
              filePath={activeDiff.filePath}
              original={activeDiff.oldContent}
              modified={activeDiff.newContent}
            />
          ) : selectedFile ? (
            <VscodeCodeEditor filePath={selectedFile} value={fileContent} onChange={setFileContent} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-[#9da1a6]">
              Create or select a file to edit
            </div>
          )}
        </div>
      </main>

      {/* Right resize divider */}
      <ResizeDivider onDrag={handleRightResize} direction="right" />

      {/* Right - Chat */}
      <aside
        className="flex flex-col border-l border-[#2d2d2d] bg-[#252526]"
        style={{ width: rightPaneWidth, minWidth: rightPaneWidth }}
      >
        <div className="flex h-9 items-center justify-between border-b border-[#2d2d2d] px-4">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[#9da1a6]">
            Sentinel-RAG
          </span>
          <span className="text-[10px] text-[#9da1a6]">{status}</span>
        </div>

        <div className="flex-1 overflow-auto p-3 space-y-3">
          {messages.map((m) => {
            if (m.role === "reasoning") {
              const preview =
                m.content.length > 140 ? `${m.content.slice(0, 140).trimEnd()}…` : m.content;
              return (
                <details key={m.id} className="rounded border border-[#4ec9b0]/30 bg-[#4ec9b0]/10 p-2">
                  <summary className="cursor-pointer list-none">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-[#4ec9b0]">
                        <span className="inline-block h-2 w-2 rounded-full bg-[#4ec9b0]" />
                        Thinking
                      </div>
                      <span className="rounded border border-[#4ec9b0]/30 bg-[#1e1e1e] px-2 py-0.5 text-[10px] text-[#4ec9b0]">
                        View
                      </span>
                    </div>
                    <div className="mt-1 max-h-10 overflow-hidden text-[12px] text-[#4ec9b0]/80 italic whitespace-pre-wrap">
                      {preview}
                    </div>
                  </summary>
                  <div className="mt-2 text-[12px] text-[#4ec9b0]/80 italic whitespace-pre-wrap">
                    {m.content}
                  </div>
                </details>
              );
            }

            if (m.role === "tool") {
              const toolTitle = m.toolName || "tool";
              const statusLabel = m.toolStatus === "running" ? "Running…" : "View";
              return (
                <details key={m.id} className="rounded border border-[#3c3c3c] bg-[#1e1e1e] p-2">
                  <summary className="cursor-pointer list-none">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[10px] font-semibold uppercase text-[#569cd6]">
                        Tool: {toolTitle}
                      </div>
                      <span
                        className={`rounded border px-2 py-0.5 text-[10px] ${
                          m.toolStatus === "running"
                            ? "border-[#3c3c3c] bg-[#252526] text-[#9da1a6]"
                            : "border-[#3c3c3c] bg-[#252526] text-[#d4d4d4]"
                        }`}
                      >
                        {statusLabel}
                      </span>
                    </div>
                    {m.toolArgs && (
                      <div className="mt-1 max-h-10 overflow-hidden text-[11px] text-[#9da1a6] whitespace-pre-wrap">
                        {m.toolArgs}
                      </div>
                    )}
                  </summary>
                  {m.toolArgs && (
                    <div className="mt-2">
                      <div className="text-[10px] font-semibold uppercase text-[#9da1a6] mb-1">Input</div>
                      <pre className="text-[11px] text-[#9da1a6] whitespace-pre-wrap overflow-auto max-h-40">
                        {m.toolArgs}
                      </pre>
                    </div>
                  )}
                  {m.toolOutput && (
                    <div className="mt-2">
                      <div className="text-[10px] font-semibold uppercase text-[#9da1a6] mb-1">Output</div>
                      {(() => {
                        const diffData = isDiffData(m.toolOutput);
                        if (diffData && m.toolName === "apply_patch") {
                          return <DiffViewer data={diffData} />;
                        }
                        return (
                          <pre className="text-[11px] text-[#9da1a6] whitespace-pre-wrap overflow-auto max-h-56">
                            {m.toolOutput}
                          </pre>
                        );
                      })()}
                    </div>
                  )}
                </details>
              );
            }

            return (
              <div
                key={m.id}
                className={`rounded-lg p-3 ${
                  m.role === "user" ? "bg-[#094771] ml-8" : "bg-[#2d2d2d] mr-8"
                }`}
              >
                <Markdown content={m.content} />
              </div>
            );
          })}
          {isStreaming && (
            <div className="flex items-center gap-2 text-xs text-[#9da1a6]">
              <span className="inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#9da1a6] [animation-delay:-0.2s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#9da1a6] [animation-delay:-0.1s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#9da1a6]" />
              </span>
              <span>Working…</span>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <div className="border-t border-[#2d2d2d] p-3">
          <textarea
            className="w-full resize-none rounded border border-[#2d2d2d] bg-[#1e1e1e] p-2 text-sm text-[#d4d4d4] outline-none focus:border-[#007acc]"
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Ask me to scan and fix your IaC files..."
            disabled={isStreaming}
          />
          <div className="mt-2 flex justify-between items-center">
            <span className="text-[10px] text-[#9da1a6]">Enter to send</span>
            <button
              onClick={sendMessage}
              disabled={isStreaming || !input.trim()}
              className="rounded bg-[#007acc] px-4 py-1.5 text-xs font-medium text-white hover:bg-[#1385d3] disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}
