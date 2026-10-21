// Local display translation. English messages are the catalog keys, so older
// packs safely leave new copy in English. No requests go to a translation service.
// Translate text nodes, never HTML: SVG geometry, handlers and data stay intact.
const WakuI18n = (() => {
  const supported = ["en", "zh-CN"];
  const attributes = ["title", "aria-label", "placeholder"];
  const originals = new WeakMap();
  const ignored = "[data-i18n-skip],script,style,pre,code,textarea,[contenteditable],"
    + ".bubble,.fc,.dbcell,.qexample,.list-title,.list-meta,.report-title,.report-card li,.kept li,.mc-name,.badge-value";
  let language = "en", saving = false, observer = null, queued = false;
  const dirty = new Set();
  try {
    const saved = localStorage.getItem("waku-ui-language");
    if (supported.includes(saved)) language = saved;
  } catch(e){ /* storage can be unavailable in a private or embedded browser */ }
  const pack = typeof WAKU_ZH_CN === "undefined" ? {messages: {}, patterns: []} : WAKU_ZH_CN;
  const patterns = pack.patterns.map(([source, replacement]) => [new RegExp(source), replacement]);

  function translate(text, locale = language){
    if (locale !== "zh-CN" || typeof text !== "string") return text;
    const key = text.replace(/\s+/g, " ").trim();
    if (!key) return text;
    let value = Object.hasOwn(pack.messages, key) ? pack.messages[key] : null;
    if (value === null){
      for (const [regex, replacement] of patterns){
        if (regex.test(key)){ value = key.replace(regex, replacement); break; }
      }
    }
    if (value === null) return text;
    return text.match(/^\s*/)[0] + value + text.match(/\s*$/)[0];
  }

  function protectedElement(el){
    if (!el || el.closest(ignored)) return true;
    // Table cells carry records, including user facts, SQL and benchmark inputs.
    // Only authored action labels inside a cell are display copy.
    return !!el.closest("td") && !el.closest("button");
  }

  function display(node, key, value, write){
    let fields = originals.get(node);
    if (!fields){ fields = new Map(); originals.set(node, fields); }
    let record = fields.get(key);
    if (!record){ record = {source: value, last: value}; fields.set(key, record); }
    if (value !== record.last) record.source = value;
    const rendered = translate(record.source);
    record.last = rendered;
    if (value !== rendered) write(rendered);
  }

  // Async button feedback must restore the source label, even if the user
  // switches languages while a clipboard or model request is in progress.
  function sourceText(el){
    return [...el.childNodes].map(node => node.nodeType === Node.TEXT_NODE
      ? (originals.get(node)?.get("text")?.source ?? node.data) : sourceText(node)).join("");
  }

  function apply(root = document.body){
    if (!root || !root.isConnected) return;
    if (root.nodeType === Node.TEXT_NODE){
      if (!protectedElement(root.parentElement))
        display(root, "text", root.data, value => { root.data = value; });
      return;
    }
    const elements = root.nodeType === Node.ELEMENT_NODE ? [root, ...root.querySelectorAll("*")] : [];
    for (const el of elements){
      // A textarea's value is user input, but its placeholder is display copy.
      const skipAttributes = el.closest("[data-i18n-skip],pre,code,[contenteditable]")
        || (protectedElement(el) && el.tagName !== "TEXTAREA");
      if (!skipAttributes){
        for (const attr of attributes){
          if (el.hasAttribute(attr))
            display(el, attr, el.getAttribute(attr), value => el.setAttribute(attr, value));
        }
      }
      if (protectedElement(el)) continue;
      for (const child of el.childNodes){
        if (child.nodeType === Node.TEXT_NODE)
          display(child, "text", child.data, value => { child.data = value; });
      }
    }
  }

  function watch(){
    observer.observe(document.body, {subtree: true, childList: true, characterData: true,
      attributes: true, attributeFilter: attributes});
  }
  function flush(){
    queued = false;
    observer.disconnect();
    for (const root of dirty) apply(root);
    dirty.clear();
    watch();
  }
  function setDisplay(value){
    language = supported.includes(value) ? value : "en";
    document.documentElement.lang = language;
    const select = document.getElementById("ui-language");
    if (select) select.value = language;
    try { localStorage.setItem("waku-ui-language", language); } catch(e){}
    if (observer) observer.disconnect();
    apply();
    if (observer) watch();
  }
  function sync(value){ if (!saving && supported.includes(value) && value !== language) setDisplay(value); }

  async function change(value){
    if (!supported.includes(value) || saving) return;
    const select = document.getElementById("ui-language");
    const note = document.getElementById("ui-language-note");
    const previous = language;
    saving = true;
    if (select) select.disabled = true;
    try {
      const response = await fetch("/api/settings", {method: "POST",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify({ui_language: value})});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Could not save language");
      if (typeof D !== "undefined" && D && D.settings) D.settings.ui_language = result.ui_language;
      if (note) note.textContent = "";
      setDisplay(result.ui_language);
    } catch(e){
      setDisplay(previous);
      if (note) note.textContent = "Could not save language. Please try again.";
    } finally {
      saving = false;
      if (select) select.disabled = false;
    }
  }

  function placeSelector(firstRun){
    const control = document.querySelector(".ui-language-control");
    if (!control) return;
    if (firstRun){
      const actions = document.getElementById("ph-actions");
      if (actions && control.parentElement !== actions) actions.append(control);
    } else {
      const footer = document.querySelector("#nav .r-bottom");
      if (footer && control.nextElementSibling !== footer) footer.before(control);
    }
  }

  function start(){
    // The compact embedded toolbar follows the saved language without adding
    // another control to its single row. The full dashboard owns the selector.
    const host = document.querySelector("#nav .r-bottom");
    if (host){
      const label = document.createElement("label");
      label.className = "ui-language-control";
      label.innerHTML = '<span>Language</span><select id="ui-language" aria-label="Interface language"'
        + ' title="Interface language"><option value="en">English</option><option value="zh-CN">简体中文</option></select>'
        + '<span id="ui-language-note" role="status"></span>';
      host.before(label);
      label.querySelector("select").addEventListener("change", e => change(e.target.value));
      placeSelector(document.body.classList.contains("first-run"));
    }
    setDisplay(language);
    observer = new MutationObserver(records => {
      for (const record of records){
        if (record.type === "childList") record.addedNodes.forEach(node => dirty.add(node));
        else dirty.add(record.target);
      }
      if (!queued && dirty.size){ queued = true; queueMicrotask(flush); }
    });
    watch();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  return {translate, sync, change, apply, sourceText, placeSelector, get language(){ return language; }};
})();
