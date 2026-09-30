"""State capture scripts are read-only except for a transient mutation observer."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser

INIT = """(() => {
  const state = {epoch: 0, documentId: crypto.randomUUID()};
  Object.defineProperty(window, '__frictionlabState', {value: state});
  new MutationObserver(() => { state.epoch += 1; }).observe(document, {
    subtree: true, childList: true, attributes: true, characterData: true
  });
})();"""

READ = """() => {
  const active = document.activeElement;
  const viewport = window.visualViewport;
  const visible = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (!node.textContent.trim() || ['SCRIPT','STYLE'].includes(node.parentElement?.tagName)) continue;
    const range = document.createRange(); range.selectNodeContents(node);
    if (Array.from(range.getClientRects()).some(rect => rect.width > 0 && rect.height > 0 &&
        rect.bottom > (viewport?.offsetTop || 0) && rect.top < (viewport?.offsetTop || 0) + (viewport?.height || innerHeight) &&
        rect.right > (viewport?.offsetLeft || 0) && rect.left < (viewport?.offsetLeft || 0) + (viewport?.width || innerWidth)))
      visible.push(node.textContent.trim());
  }
  return {
    document_id: window.__frictionlabState.documentId,
    mutation_epoch: window.__frictionlabState.epoch,
    text: document.body.innerText,
    visible_text: visible.join(' '),
    focus: {id: active?.id || '', tag: active?.tagName?.toLowerCase() || '',
      name: active?.getAttribute('aria-label') || active?.innerText?.slice(0, 200) || '',
      role: active?.getAttribute('role') || ''},
    validation: Array.from(document.querySelectorAll('[role="alert"], [aria-invalid="true"]'))
      .filter(el => el.getClientRects().length).map(el => el.innerText || el.getAttribute('aria-describedby') || ''),
    inputs: Array.from(document.querySelectorAll('input')).map(el => [el.id, el.value, el.disabled]),
    scroll: [window.scrollX, window.scrollY],
    coordinates: {offset_x: viewport?.offsetLeft || 0, offset_y: viewport?.offsetTop || 0,
      css_width: viewport?.width || innerWidth, css_height: viewport?.height || innerHeight,
      pixel_width: innerWidth, pixel_height: innerHeight},
    dom: document.documentElement.outerHTML
  };
}"""

SANITIZED_DOM = """() => {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelectorAll('script,style,link,iframe,object,embed').forEach(el => el.remove());
  clone.querySelectorAll('*').forEach(el => {
    Array.from(el.attributes).forEach(attr => {
      if (/^on/i.test(attr.name) || ['src','srcset','href','action','formaction','value','nonce'].includes(attr.name))
        el.removeAttribute(attr.name);
    });
  });
  return clone.outerHTML;
}"""


def redact(text):
    return re.sub(r"[\w.+-]+@[\w.-]+", "[redacted email]", text)


def fingerprint(state):
    raw = {
        key: state[key]
        for key in ("document_id", "mutation_epoch", "dom", "inputs", "scroll", "coordinates")
    }
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


def semantic_signature(state):
    # Focus movement is stored separately: merely focusing a dead button is not progress.
    return hashlib.sha256(redact(state["text"]).encode()).hexdigest()


def attribute_shape(source):
    class Shape(HTMLParser):
        def __init__(self):
            super().__init__()
            self.nodes = []

        def handle_starttag(self, tag, attrs):
            self.nodes.append({"tag": tag, "attribute_names": sorted(key for key, _ in attrs)})

    parser = Shape()
    parser.feed(source)
    return parser.nodes
