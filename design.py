"""A quiet product shell: system typography, whitespace, progressive disclosure."""
from html import escape

import streamlit as st


def install_design():
    st.markdown('''<style>
    :root{--ink:#1d1d1f;--muted:#6e6e73;--blue:#0071e3;--line:#e7e7eb;--paper:#f5f5f7}
    html,body,.stApp p,.stApp input,.stApp button,.stApp label,h1,h2,h3{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .stApp{background:var(--paper);color:var(--ink)}
    [data-testid="stHeader"]{background:transparent}
    [data-testid="stToolbar"]{display:none}
    .block-container{max-width:1060px;padding:1.7rem 2.8rem 4rem}
    h1,h2,h3{letter-spacing:-.035em!important;color:var(--ink)!important}
    h1{font-weight:650!important}p{line-height:1.6}
    [data-testid="stCaptionContainer"]{color:var(--muted)}
    .st-key-trip_form,.st-key-trip_summary,.st-key-offer_input,[class*="st-key-stay_card_"]{border:1px solid var(--line)!important;border-radius:24px!important;background:#fff!important;padding:22px!important}
    .st-key-page [data-testid="stRadioGroup"]{gap:4px;padding:4px;background:#eaeaee;border-radius:999px;flex-wrap:nowrap}
    .st-key-page [data-testid="stRadioOption"]{padding:7px 12px;border-radius:999px;color:var(--muted)}
    .st-key-page [data-testid="stRadioOption"][data-selected="true"]{background:white;color:var(--ink);box-shadow:0 1px 4px #0000000c}
    .st-key-page [data-testid="stRadioOption"]>div>div:first-child{display:none}
    .st-key-page [data-testid="stRadioOption"]:focus-within{outline:2px solid var(--blue);outline-offset:2px}
    .st-key-page [data-testid="stRadioOption"] p{white-space:nowrap;font-size:13px}

    [data-testid="stExpander"]{border:1px solid var(--line);border-radius:16px;background:white}
    [data-testid="stExpander"] summary{font-size:14px!important}
    [data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-baseweb="select"]>div{border-radius:12px!important}
    [data-testid="stTextArea"] textarea{border-radius:14px!important}
    .stButton button,.stDownloadButton button{border-radius:999px!important;min-height:42px;font-weight:550;border-color:var(--line)}
    .stButton button[kind="primary"]{background:var(--blue);border-color:var(--blue);color:white}
    [data-testid="stRadio"]>div[role="radiogroup"]{gap:1.8rem}
    [data-testid="stRadio"] label p{font-size:14px}
    [data-testid="stMetricValue"]{font-size:30px;letter-spacing:-.04em}
    .brand{display:flex;align-items:center;gap:10px;font-size:23px;font-weight:700;letter-spacing:-1px;padding:6px 0 20px}
    .brand-mark{width:27px;height:27px;border-radius:8px;background:var(--ink);color:white;display:inline-flex;align-items:center;justify-content:center;font-size:16px;letter-spacing:-3px;padding-right:3px}
    .brand small{font-size:10px;letter-spacing:1.4px;color:var(--muted);font-weight:500;margin-left:5px}
    .hero{padding:32px 0 26px}.eyebrow{font-size:11px;font-weight:650;letter-spacing:1.7px;text-transform:uppercase;color:var(--blue);margin:0 0 14px}
    .hero h1{font-size:60px;line-height:1.06;font-weight:650;margin:0 0 18px;max-width:700px;letter-spacing:-3px}
    .hero.compact{padding:18px 0 16px}.hero.compact h1{font-size:44px;letter-spacing:-2px;margin-bottom:10px}
    .hero p{font-size:18px;color:var(--muted);max-width:620px;line-height:1.5;margin:0}
    .quiet-note{font-size:12px;color:var(--muted);margin:8px 0 18px}
    .pill{max-width:100%;overflow-wrap:anywhere;display:inline-block;font-size:11px;background:#eaf2fc;color:#185b9c;border-radius:999px;padding:5px 10px;margin-right:7px;line-height:1.4}
    .pill.neutral{background:#f0f0f3;color:var(--muted)}
    .summary{padding:4px 5px 12px}.summary .amount{font-size:64px;letter-spacing:-3px;font-weight:650;line-height:1.12;margin:9px 0 14px}
    .summary .label{font-size:13px;color:var(--muted)}.summary .support{font-size:15px;color:var(--muted);line-height:1.8}
    .summary .saving{display:inline-block;color:#21724a;background:#edf7f0;border-radius:999px;padding:5px 12px;font-size:12px;margin-top:14px}
    .stay{padding:5px 3px 2px}.stay .city{font-size:11px;color:var(--muted);letter-spacing:1.4px;font-weight:600;text-transform:uppercase;margin-bottom:10px}
    .stay h3{font-size:25px;line-height:1.2;margin:0 0 9px;font-weight:620}.stay .meta{font-size:14px;color:var(--muted);margin-bottom:13px}
    .stay-price{text-align:right;padding:7px 0}.stay-price strong{font-size:28px;font-weight:600;letter-spacing:-1px}.stay-price p{font-size:12px;color:var(--muted);margin:1px 0}
    .feature{border-top:1px solid var(--line);padding:20px 10px 18px 0}.feature b{font-size:14px;font-weight:600}.feature p{font-size:13px;color:var(--muted);line-height:1.55;margin-top:7px}
    .step-number{font-size:12px;color:var(--blue);margin-bottom:10px;font-weight:600}.footer{border-top:1px solid var(--line);padding:20px 0 0;margin-top:35px;color:var(--muted);font-size:11px}
    @media(max-width:700px){.block-container{padding:1rem 1.1rem 3rem}.hero{padding:20px 0}.hero h1{font-size:42px;letter-spacing:-2px}.hero p{font-size:16px}.summary .amount{font-size:50px}.stay-price{text-align:left}.brand small{display:none}}
    </style>''', unsafe_allow_html=True)


def hero(eyebrow, title, description, compact=False):
    st.markdown(f'<section class="hero{" compact" if compact else ""}"><div class="eyebrow">{escape(eyebrow)}</div>'
                f'<h1>{escape(title).replace(chr(10), "<br>")}</h1><p>{escape(description)}</p></section>',unsafe_allow_html=True)


def feature(title, description, number=''):
    st.markdown(f'<div class="feature"><div class="step-number">{escape(number)}</div>'
                f'<b>{escape(title)}</b><p>{escape(description)}</p></div>',unsafe_allow_html=True)
