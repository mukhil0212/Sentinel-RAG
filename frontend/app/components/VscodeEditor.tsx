"use client";

import { useMemo, useState } from "react";
import Editor, { DiffEditor, type Monaco } from "@monaco-editor/react";

function getLanguageId(filePath: string | null): string {
  if (!filePath) return "plaintext";
  const name = filePath.toLowerCase();
  const ext = name.split(".").pop() ?? "";

  if (ext === "ts" || ext === "tsx") return "typescript";
  if (ext === "js" || ext === "jsx") return "javascript";
  if (ext === "json") return "json";
  if (ext === "md") return "markdown";
  if (ext === "py") return "python";
  if (ext === "sql") return "sql";
  if (ext === "sh") return "shell";
  if (ext === "yml" || ext === "yaml") return "yaml";
  if (ext === "tf" || ext === "tfvars" || name.endsWith(".terraform.lock.hcl")) return "hcl";

  return "plaintext";
}

let monacoSetupStarted = false;
async function setupMonaco(monaco: Monaco) {
  // Register a couple of basic languages that aren't always enabled by default.
  // This keeps Terraform/YAML readable without bringing in extra language plugins.
  const registerBasic = async (id: string, modPath: string) => {
    if (monaco.languages.getLanguages().some((lang) => lang.id === id)) return;
    try {
      const mod = (await import(
        /* webpackChunkName: "monaco-basic-lang" */ modPath
      )) as { language?: unknown; conf?: unknown };
      if (!mod?.language) return;
      monaco.languages.register({ id });
      monaco.languages.setMonarchTokensProvider(
        id,
        mod.language as Parameters<Monaco["languages"]["setMonarchTokensProvider"]>[1]
      );
      if (mod.conf) {
        monaco.languages.setLanguageConfiguration(
          id,
          mod.conf as Parameters<Monaco["languages"]["setLanguageConfiguration"]>[1]
        );
      }
    } catch {
      // ignore: language remains plaintext
    }
  };

  await Promise.all([
    registerBasic("yaml", "monaco-editor/esm/vs/basic-languages/yaml/yaml"),
    registerBasic("hcl", "monaco-editor/esm/vs/basic-languages/hcl/hcl"),
  ]);
}

function ensureMonacoSetup(monaco: Monaco) {
  if (monacoSetupStarted) return;
  monacoSetupStarted = true;
  void setupMonaco(monaco);
}

export function VscodeCodeEditor({
  filePath,
  value,
  onChange,
  readOnly,
}: {
  filePath: string | null;
  value: string;
  onChange: (nextValue: string) => void;
  readOnly?: boolean;
}) {
  const language = useMemo(() => getLanguageId(filePath), [filePath]);

  return (
    <Editor
      value={value}
      language={language}
      theme="vs-dark"
      options={{
        readOnly: !!readOnly,
        minimap: { enabled: false },
        fontSize: 13,
        lineNumbers: "on",
        scrollBeyondLastLine: false,
        automaticLayout: true,
        wordWrap: "on",
        renderWhitespace: "none",
      }}
      beforeMount={ensureMonacoSetup}
      onChange={(nextValue: string | undefined) => onChange(nextValue ?? "")}
    />
  );
}

export function VscodeDiffViewer({
  filePath,
  original,
  modified,
  onToggleMode,
}: {
  filePath: string | null;
  original: string;
  modified: string;
  onToggleMode?: (mode: "split" | "unified") => void;
}) {
  const [mode, setMode] = useState<"split" | "unified">("split");
  const language = useMemo(() => getLanguageId(filePath), [filePath]);

  return (
    <div className="h-full flex flex-col bg-[#0d1117]">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#30363d] bg-[#161b22]">
        <div className="text-xs text-[#d4d4d4] truncate">{filePath ?? "Diff"}</div>
        <div className="flex rounded overflow-hidden border border-[#30363d]">
          <button
            onClick={() => {
              setMode("split");
              onToggleMode?.("split");
            }}
            className={`px-3 py-1 text-[10px] ${
              mode === "split"
                ? "bg-[#30363d] text-[#e6edf3]"
                : "bg-transparent text-[#8b949e] hover:text-[#e6edf3]"
            }`}
          >
            Split
          </button>
          <button
            onClick={() => {
              setMode("unified");
              onToggleMode?.("unified");
            }}
            className={`px-3 py-1 text-[10px] ${
              mode === "unified"
                ? "bg-[#30363d] text-[#e6edf3]"
                : "bg-transparent text-[#8b949e] hover:text-[#e6edf3]"
            }`}
          >
            Unified
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <DiffEditor
          original={original}
          modified={modified}
          language={language}
          theme="vs-dark"
          options={{
            readOnly: true,
            renderSideBySide: mode === "split",
            minimap: { enabled: false },
            fontSize: 13,
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
          beforeMount={ensureMonacoSetup}
        />
      </div>
    </div>
  );
}
