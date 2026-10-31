"""`python -m app ui`: the Hebrew, right-to-left Streamlit chat (entry script).

Why this file is so small: Streamlit runs it top to bottom on every interaction,
and the page's modules pull in torch, chromadb and openai, which take seconds
to import on a cold start. So the title and a loading message go on the page
first, and only then is the page module imported (once per process) and drawn.
"""

from __future__ import annotations

import streamlit as st

from app import ui_text as text

# Fixed CSS, no user text: the page reads right to left; Latin names such as GV80
# inside a Hebrew sentence are ordered by the browser's bidi algorithm.
RTL_CSS = """
<style>
.stApp, [data-testid="stSidebar"], [data-testid="stChatMessage"] { direction: rtl; }
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
[data-testid="stExpander"] summary, h1, h2, h3 { text-align: right; }
[data-testid="stChatInput"] textarea { direction: rtl; text-align: right; }
[data-testid="stMarkdownContainer"] table { direction: rtl; margin-inline-start: 0; }
[data-testid="stMarkdownContainer"] th,
[data-testid="stMarkdownContainer"] td { text-align: right; }
</style>
"""


st.set_page_config(page_title="carwise", page_icon="🚗")
st.markdown(RTL_CSS, unsafe_allow_html=True)
st.title(text.TITLE)
with st.spinner(text.LOADING):
    from app import ui_page  # noqa: E402  (after the title on purpose, see above)
ui_page.render()
