"""Output formatting and browser-side helpers for AI coaching."""
from __future__ import annotations

import json
import re
import time

import streamlit as st

from models.coach_tool_presenter import format_tool_result as format_tool_result  # noqa: F401 — re-export


def speak_text(text: str, voice: str = "default"):
    """Озвучивает текст с помощью Web Speech API через JavaScript."""
    del voice  # Voice selection is currently browser-driven.

    clean_text = text
    clean_text = re.sub(r"^#+\s+", "", clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r"\*\*(.+?)\*\*", r"\1", clean_text)
    clean_text = re.sub(r"\*(.+?)\*", r"\1", clean_text)
    clean_text = re.sub(r"`(.+?)`", r"\1", clean_text)
    clean_text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", clean_text)

    if len(clean_text) > 500:
        clean_text = clean_text[:500] + "..."

    clean_text_escaped = json.dumps(clean_text, ensure_ascii=False)

    js_code = f"""
    <script>
    (function() {{
        if ('speechSynthesis' in window) {{
            window.speechSynthesis.cancel();

            function speak() {{
                const utterance = new SpeechSynthesisUtterance({clean_text_escaped});
                utterance.lang = 'ru-RU';
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                utterance.volume = 1.0;

                const voices = window.speechSynthesis.getVoices();
                if (voices.length > 0) {{
                    let selectedVoice = voices.find(v => v.lang.startsWith('ru'));
                    if (!selectedVoice) {{
                        selectedVoice = voices[0];
                    }}
                    utterance.voice = selectedVoice;
                }}

                window.speechSynthesis.speak(utterance);
            }}

            if (window.speechSynthesis.getVoices().length > 0) {{
                speak();
            }} else {{
                window.speechSynthesis.onvoiceschanged = speak;
            }}
        }} else {{
            console.warn('Speech synthesis not supported');
        }}
    }})();
    </script>
    """

    # st.html with unsafe_allow_javascript is the post-2026-06-01 replacement
    # for the deprecated st.components.v1.html. Unlike the old API it runs the
    # <script> in the main DOM (DOMPurify-sanitized) instead of a sandboxed
    # iframe, so Web Speech API access is not restricted.
    st.html(js_code, unsafe_allow_javascript=True)


def simulate_streaming_response(placeholder, text):
    """Симулирует стриминг вывода текста для лучшего UX."""
    if len(text) <= 100:
        placeholder.markdown(text)
        return

    sentences = re.findall(r".+?(?:[.!?](?:\s+|$)|:\n|\n\n|$)", text, flags=re.DOTALL)

    current_text = ""

    for i, sentence in enumerate(sentences):
        current_text += sentence

        if i < len(sentences) - 1:
            display_text = current_text + " ▋"
        else:
            display_text = current_text

        placeholder.markdown(display_text)

        if len(sentence) > 50:
            time.sleep(0.25)
        elif len(sentence) > 20:
            time.sleep(0.12)
        else:
            time.sleep(0.04)

    placeholder.markdown(current_text)
