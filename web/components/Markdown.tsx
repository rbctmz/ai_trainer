import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders coach markdown (GFM tables, bold, headings, lists, code) with
// Tailwind styles. No typography plugin needed — elements are mapped here.
export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="mb-1 mt-2 text-base font-bold text-ink">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-1 mt-2 text-sm font-bold text-ink">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-semibold text-ink">{children}</h3>,
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        a: ({ children, href }) => (
          <a href={href} className="text-tone-neutral underline" target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
        code: ({ children }) => (
          <code className="rounded bg-surface-muted px-1 py-0.5 text-[0.85em] text-ink">{children}</code>
        ),
        pre: ({ children }) => (
          <pre className="mb-2 overflow-x-auto rounded-lg bg-surface-muted p-3 text-xs">{children}</pre>
        ),
        table: ({ children }) => (
          <div className="mb-2 overflow-x-auto">
            <table className="w-full border-collapse text-xs">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border border-surface-border bg-surface-muted px-2 py-1 text-left font-semibold">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border border-surface-border px-2 py-1">{children}</td>
        ),
        blockquote: ({ children }) => (
          <blockquote className="mb-2 border-l-2 border-surface-border pl-3 text-ink-soft">
            {children}
          </blockquote>
        ),
        hr: () => <hr className="my-2 border-surface-border" />,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
