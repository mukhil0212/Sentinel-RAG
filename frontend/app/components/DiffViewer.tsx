"use client";

import { useState } from "react";

type DiffLine = {
  type: "add" | "remove" | "context" | "hunk";
  content: string;
};

type DiffData = {
  message: string;
  operation_type: "create_file" | "update_file" | "delete_file";
  file_path: string;
  diff_lines: DiffLine[];
  old_content: string;
  new_content: string;
};

type DiffViewerProps = {
  data: DiffData;
};

// Compute line numbers for old and new content
function computeLineNumbers(lines: DiffLine[]): { oldLine: number | null; newLine: number | null }[] {
  let oldLine = 0;
  let newLine = 0;

  return lines.map((line) => {
    if (line.type === "hunk") {
      // Parse hunk header to get starting line numbers
      // Format: @@ -oldStart,oldCount +newStart,newCount @@
      const match = line.content.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (match) {
        oldLine = parseInt(match[1], 10) - 1;
        newLine = parseInt(match[2], 10) - 1;
      }
      return { oldLine: null, newLine: null };
    }

    if (line.type === "remove") {
      oldLine++;
      return { oldLine, newLine: null };
    }

    if (line.type === "add") {
      newLine++;
      return { oldLine: null, newLine };
    }

    // Context line
    oldLine++;
    newLine++;
    return { oldLine, newLine };
  });
}

export function DiffViewer({ data }: DiffViewerProps) {
  const [viewMode, setViewMode] = useState<"unified" | "split">("unified");

  const { operation_type, file_path, diff_lines } = data;

  // Calculate stats
  const additions = diff_lines.filter((l) => l.type === "add").length;
  const deletions = diff_lines.filter((l) => l.type === "remove").length;

  const lineNumbers = computeLineNumbers(diff_lines);

  // Operation-specific styling
  const opStyles = {
    create_file: { bg: "bg-[#238636]/20", border: "border-[#238636]/40", label: "Created", icon: "+" },
    update_file: { bg: "bg-[#1f6feb]/20", border: "border-[#1f6feb]/40", label: "Modified", icon: "~" },
    delete_file: { bg: "bg-[#da3633]/20", border: "border-[#da3633]/40", label: "Deleted", icon: "-" },
  };

  const opStyle = opStyles[operation_type] || opStyles.update_file;

  if (viewMode === "split") {
    return (
      <SplitDiffView
        data={data}
        opStyle={opStyle}
        additions={additions}
        deletions={deletions}
        setViewMode={setViewMode}
      />
    );
  }

  return (
    <div className={`rounded border ${opStyle.border} ${opStyle.bg} overflow-hidden`}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#3c3c3c] bg-[#161b22]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#30363d] text-[#8b949e]">
            {opStyle.icon}
          </span>
          <span className="text-xs text-[#e6edf3] font-mono">{file_path}</span>
          <span className="text-[10px] text-[#8b949e]">({opStyle.label})</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-[#3fb950]">+{additions}</span>
            <span className="text-[#f85149]">-{deletions}</span>
          </div>
          <div className="flex rounded overflow-hidden border border-[#30363d]">
            <button
              onClick={() => setViewMode("unified")}
              className="px-2 py-0.5 text-[10px] bg-[#30363d] text-[#e6edf3]"
            >
              Unified
            </button>
            <button
              onClick={() => setViewMode("split")}
              className="px-2 py-0.5 text-[10px] bg-transparent text-[#8b949e] hover:text-[#e6edf3]"
            >
              Split
            </button>
          </div>
        </div>
      </div>

      {/* Diff content */}
      <div className="overflow-auto max-h-80 font-mono text-[11px]">
        {diff_lines.length === 0 ? (
          <div className="p-3 text-[#8b949e] text-center italic">No changes to display</div>
        ) : (
          <table className="w-full border-collapse">
            <tbody>
              {diff_lines.map((line, idx) => {
                const { oldLine, newLine } = lineNumbers[idx];

                if (line.type === "hunk") {
                  return (
                    <tr key={idx} className="bg-[#161b22]">
                      <td className="w-10 text-right px-2 py-0.5 text-[#484f58] select-none border-r border-[#30363d]">
                        ...
                      </td>
                      <td className="w-10 text-right px-2 py-0.5 text-[#484f58] select-none border-r border-[#30363d]">
                        ...
                      </td>
                      <td className="px-2 py-0.5 text-[#8b949e]">{line.content}</td>
                    </tr>
                  );
                }

                const lineStyles = {
                  add: {
                    bg: "bg-[#238636]/20",
                    numBg: "bg-[#238636]/30",
                    text: "text-[#aff5b4]",
                    prefix: "+",
                  },
                  remove: {
                    bg: "bg-[#da3633]/20",
                    numBg: "bg-[#da3633]/30",
                    text: "text-[#ffa198]",
                    prefix: "-",
                  },
                  context: {
                    bg: "bg-transparent",
                    numBg: "bg-transparent",
                    text: "text-[#8b949e]",
                    prefix: " ",
                  },
                };

                const style = lineStyles[line.type] || lineStyles.context;

                return (
                  <tr key={idx} className={style.bg}>
                    <td
                      className={`w-10 text-right px-2 py-0.5 text-[#484f58] select-none border-r border-[#30363d] ${style.numBg}`}
                    >
                      {oldLine ?? ""}
                    </td>
                    <td
                      className={`w-10 text-right px-2 py-0.5 text-[#484f58] select-none border-r border-[#30363d] ${style.numBg}`}
                    >
                      {newLine ?? ""}
                    </td>
                    <td className={`px-2 py-0.5 ${style.text} whitespace-pre`}>
                      <span className="select-none mr-2 text-[#6e7681]">{style.prefix}</span>
                      {line.content}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// Split view component
function SplitDiffView({
  data,
  opStyle,
  additions,
  deletions,
  setViewMode,
}: {
  data: DiffData;
  opStyle: { bg: string; border: string; label: string; icon: string };
  additions: number;
  deletions: number;
  setViewMode: (mode: "unified" | "split") => void;
}) {
  const { file_path, old_content, new_content } = data;

  const oldLines = old_content.split("\n");
  const newLines = new_content.split("\n");

  return (
    <div className={`rounded border ${opStyle.border} ${opStyle.bg} overflow-hidden`}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#3c3c3c] bg-[#161b22]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#30363d] text-[#8b949e]">
            {opStyle.icon}
          </span>
          <span className="text-xs text-[#e6edf3] font-mono">{file_path}</span>
          <span className="text-[10px] text-[#8b949e]">({opStyle.label})</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-[#3fb950]">+{additions}</span>
            <span className="text-[#f85149]">-{deletions}</span>
          </div>
          <div className="flex rounded overflow-hidden border border-[#30363d]">
            <button
              onClick={() => setViewMode("unified")}
              className="px-2 py-0.5 text-[10px] bg-transparent text-[#8b949e] hover:text-[#e6edf3]"
            >
              Unified
            </button>
            <button
              onClick={() => setViewMode("split")}
              className="px-2 py-0.5 text-[10px] bg-[#30363d] text-[#e6edf3]"
            >
              Split
            </button>
          </div>
        </div>
      </div>

      {/* Split diff content */}
      <div className="overflow-auto max-h-80 font-mono text-[11px]">
        <div className="grid grid-cols-2 divide-x divide-[#30363d]">
          {/* Old content */}
          <div className="min-w-0">
            <div className="px-2 py-1 bg-[#da3633]/10 border-b border-[#30363d] text-[10px] text-[#ffa198]">
              Original
            </div>
            <div className="overflow-auto">
              {oldLines.map((line, idx) => (
                <div key={idx} className="flex hover:bg-[#161b22]">
                  <span className="w-8 flex-shrink-0 text-right px-2 py-0.5 text-[#484f58] select-none bg-[#0d1117] border-r border-[#30363d]">
                    {idx + 1}
                  </span>
                  <span className="px-2 py-0.5 text-[#8b949e] whitespace-pre overflow-hidden text-ellipsis">
                    {line}
                  </span>
                </div>
              ))}
              {oldLines.length === 0 && (
                <div className="p-2 text-[#484f58] italic">Empty file</div>
              )}
            </div>
          </div>

          {/* New content */}
          <div className="min-w-0">
            <div className="px-2 py-1 bg-[#238636]/10 border-b border-[#30363d] text-[10px] text-[#3fb950]">
              Updated
            </div>
            <div className="overflow-auto">
              {newLines.map((line, idx) => (
                <div key={idx} className="flex hover:bg-[#161b22]">
                  <span className="w-8 flex-shrink-0 text-right px-2 py-0.5 text-[#484f58] select-none bg-[#0d1117] border-r border-[#30363d]">
                    {idx + 1}
                  </span>
                  <span className="px-2 py-0.5 text-[#aff5b4] whitespace-pre overflow-hidden text-ellipsis">
                    {line}
                  </span>
                </div>
              ))}
              {newLines.length === 0 && (
                <div className="p-2 text-[#484f58] italic">File deleted</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper to check if output is structured diff data
export function isDiffData(output: string): DiffData | null {
  try {
    const parsed = JSON.parse(output);
    if (
      parsed &&
      typeof parsed.message === "string" &&
      typeof parsed.operation_type === "string" &&
      typeof parsed.file_path === "string" &&
      Array.isArray(parsed.diff_lines)
    ) {
      return parsed as DiffData;
    }
  } catch {
    // Not JSON, return null
  }
  return null;
}
