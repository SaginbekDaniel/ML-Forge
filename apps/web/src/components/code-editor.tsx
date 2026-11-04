"use client";

import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { bracketMatching, HighlightStyle, indentOnInput, indentUnit, syntaxHighlighting } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
  placeholder as placeholderExt,
} from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { useEffect, useRef } from "react";

// Colours come from CSS variables so the editor follows the app theme.
const theme = EditorView.theme({
  "&": { height: "100%", backgroundColor: "var(--code-bg)", color: "var(--text)", fontSize: "13px" },
  ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.55" },
  ".cm-content": { padding: "10px 0", caretColor: "var(--accent)" },
  ".cm-gutters": { backgroundColor: "var(--code-bg)", color: "var(--text-subtle)", border: "none" },
  ".cm-activeLine": { backgroundColor: "color-mix(in srgb, var(--surface-3) 45%, transparent)" },
  ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--text-muted)" },
  "&.cm-focused": { outline: "none" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "var(--selection) !important" },
  ".cm-cursor": { borderLeftColor: "var(--accent)" },
  ".cm-matchingBracket": { backgroundColor: "var(--accent-soft)", outline: "1px solid var(--border-strong)" },
  ".cm-placeholder": { color: "var(--text-subtle)" },
});

const highlight = HighlightStyle.define([
  { tag: [tags.keyword, tags.controlKeyword, tags.operatorKeyword, tags.definitionKeyword], color: "var(--syntax-keyword)" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--syntax-string)" },
  { tag: [tags.number, tags.bool, tags.null], color: "var(--syntax-number)" },
  { tag: tags.comment, color: "var(--syntax-comment)", fontStyle: "italic" },
  { tag: [tags.function(tags.variableName), tags.function(tags.propertyName)], color: "var(--syntax-function)" },
  { tag: [tags.definition(tags.variableName), tags.className], color: "var(--syntax-def)" },
]);

export interface CodeEditorProps {
  value: string;
  onChange: (code: string) => void;
  onRun?: () => void;
  onSubmit?: () => void;
  readOnly?: boolean;
  label: string;
  describedBy?: string;
  placeholder?: string;
}

/**
 * Thin CodeMirror 6 wrapper. Uncontrolled internally (no re-creation on each
 * keystroke); external `value` changes (reset, load attempt) are applied as a
 * single transaction.
 */
export function CodeEditor({ value, onChange, onRun, onSubmit, readOnly, label, describedBy, placeholder }: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const handlers = useRef({ onChange, onRun, onSubmit });
  useEffect(() => {
    handlers.current = { onChange, onRun, onSubmit };
  });

  useEffect(() => {
    if (!host.current) return;
    const runKeys = keymap.of([
      { key: "Mod-Shift-Enter", run: () => (handlers.current.onSubmit?.(), true) },
      { key: "Mod-Enter", run: () => (handlers.current.onRun?.(), true) },
    ]);
    const v = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          runKeys,
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightActiveLine(),
          history(),
          drawSelection(),
          indentOnInput(),
          bracketMatching(),
          indentUnit.of("    "),
          EditorState.tabSize.of(4),
          python(),
          syntaxHighlighting(highlight),
          theme,
          keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
          EditorView.lineWrapping,
          EditorState.readOnly.of(Boolean(readOnly)),
          EditorView.contentAttributes.of({
            "aria-label": label,
            ...(describedBy ? { "aria-describedby": describedBy } : {}),
            autocapitalize: "off",
            autocorrect: "off",
            spellcheck: "false",
          }),
          ...(placeholder ? [placeholderExt(placeholder)] : []),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) handlers.current.onChange(u.state.doc.toString());
          }),
        ],
      }),
    });
    view.current = v;
    return () => {
      v.destroy();
      view.current = null;
    };
    // Editor is created once per mount; value sync happens below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, label]);

  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) {
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
    }
  }, [value]);

  return <div ref={host} className="h-full min-h-0 overflow-hidden" data-testid="code-editor" />;
}
