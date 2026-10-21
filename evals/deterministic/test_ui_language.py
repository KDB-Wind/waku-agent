"""Dashboard language is persistent display state, independent of model state."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values

from waku import config
from waku.ops import settings_api

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "waku" / "ops" / "static"


def test_new_setting_preserves_positional_provider():
    assert config.Settings("openai").provider == "openai"


@pytest.mark.parametrize("value,expected", [(None, "en"), ("zh-CN", "zh-CN"),
                                          ("en", "en"), ("unknown", "en")])
def test_language_default_and_environment(monkeypatch, value, expected):
    monkeypatch.delenv("WAKU_UI_LANGUAGE", raising=False)
    if value is not None:
        monkeypatch.setenv("WAKU_UI_LANGUAGE", value)
    assert config.Settings().ui_language == expected


def test_language_save_survives_a_fresh_process_without_changing_model_or_soul(
        monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("WAKU_MODEL=test-model\n", encoding="utf-8")
    soul = tmp_path / "SOUL.md"
    soul.write_text("Reply in English.\n", encoding="utf-8")
    monkeypatch.setattr(config, "env_write_path", lambda: env_path)
    monkeypatch.setenv("WAKU_UI_LANGUAGE", "en")
    monkeypatch.setenv("WAKU_MODEL", "test-model")
    result = settings_api.apply_settings({"ui_language": "zh-CN"})
    assert result["ok"] is True
    assert result["ui_language"] == "zh-CN"
    assert dotenv_values(env_path) == {"WAKU_MODEL": "test-model", "WAKU_UI_LANGUAGE": "zh-CN"}
    assert soul.read_text(encoding="utf-8") == "Reply in English.\n"
    env = {key: value for key, value in os.environ.items() if key != "WAKU_UI_LANGUAGE"}
    env["PYTHONPATH"] = str(ROOT)
    process = subprocess.run(
        [sys.executable, "-c", "from waku.config import Settings; print(Settings().ui_language)"],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert process.stdout.strip() == "zh-CN"
    result = settings_api.apply_settings({"ui_language": "en"})
    assert result["ui_language"] == "en"
    assert dotenv_values(env_path)["WAKU_UI_LANGUAGE"] == "en"


@pytest.mark.parametrize("value", ["zh", "fr", "", None, True, [], {}])
def test_invalid_language_does_not_write_any_settings(monkeypatch, tmp_path, value):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config, "env_write_path", lambda: env_path)
    monkeypatch.setenv("WAKU_UI_LANGUAGE", "en")
    result = settings_api.apply_settings({"ui_language": value, "experimental": "1"})
    assert result == {"error": "ui_language must be en or zh-CN"}
    assert not env_path.exists()
    assert config.Settings().ui_language == "en"


def test_unrelated_settings_do_not_reset_language(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "env_write_path", lambda: tmp_path / ".env")
    monkeypatch.setenv("WAKU_UI_LANGUAGE", "zh-CN")
    assert settings_api.apply_settings({})["ui_language"] == "zh-CN"


def test_catalog_and_display_behavior_offline():
    """Execute the shipped JS with tiny DOM fixtures; no browser or API needed.

    Node is optional for Python-only contributors. Browser QA separately covers
    the actual DOM, navigation, SVG geometry, polling and language persistence.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the dashboard JavaScript eval")
    script = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const context = vm.createContext({document: {readyState: 'loading', addEventListener(){},
  documentElement: {}, getElementById(){ return null; }, body: null},
  localStorage: {getItem(){ return null; }}, Node: {TEXT_NODE: 3, ELEMENT_NODE: 1}});
for (const name of ['locales/zh-CN.js', 'js/i18n.js'])
  vm.runInContext(fs.readFileSync(process.argv[1] + '/' + name, 'utf8'), context);
const api = vm.runInContext('WakuI18n', context);
assert.equal(api.translate('Overview', 'zh-CN'), '概览');
assert.equal(api.translate('Overview', 'en'), 'Overview');
assert.equal(api.translate('A new upstream sentence', 'zh-CN'), 'A new upstream sentence');
assert.equal(api.translate('constructor', 'zh-CN'), 'constructor');
assert.equal(api.translate('<script>alert(1)</script>', 'zh-CN'), '<script>alert(1)</script>');
assert.equal(api.translate('  2 skip · 3 retrieve\n', 'zh-CN'), '  2 跳过 · 3 检索\n');
assert.equal(api.translate('how to act · SKILL.md · 7 skill(s)', 'zh-CN'), '行动方法 · SKILL.md · 7 个技能');
assert.equal(api.translate('4/12 queued → distilled into facts', 'zh-CN'), '4/12 条排队 → 提炼为事实');
assert.equal(api.translate('· updated 2s ago · C:/my-home', 'zh-CN'), '· 2 秒前更新 · C:/my-home');
// A closed fixture for each protected type. Even text matching a UI key is data.
for (const selector of ['[data-i18n-skip]', 'code', 'pre', 'textarea', '[contenteditable]',
  '.bubble', '.fc', '.dbcell', '.qexample', '.list-title', '.list-meta', '.report-title',
  '.report-card li', '.kept li', '.mc-name', '.badge-value', 'td']){
  const parent = {closest(query){ return query.split(',').includes(selector) ? this : null; }};
  const text = {nodeType: 3, data: 'Overview', isConnected: true, parentElement: parent};
  api.sync('zh-CN'); api.apply(text);
  assert.equal(text.data, 'Overview', selector + ' must preserve data');
}
const parent = {closest(){ return null; }, childNodes: []};
const text = {nodeType: 3, data: 'Overview', isConnected: true, parentElement: parent};
parent.childNodes.push(text);
api.apply(text); assert.equal(text.data, '概览');
assert.equal(api.sourceText(parent), 'Overview');
api.sync('en'); api.apply(text); assert.equal(text.data, 'Overview');
text.data = 'Memory'; api.sync('zh-CN'); api.apply(text); assert.equal(text.data, '记忆');
api.sync('en'); api.apply(text); assert.equal(text.data, 'Memory');
const pack = vm.runInContext('WAKU_ZH_CN', context);
for (const [key, value] of Object.entries(pack.messages)){
  assert.ok(key.trim() && typeof value === 'string' && value.trim());
  assert.equal(key, key.replace(/\s+/g, ' ').trim(), 'keys must use normalized whitespace');
}
for (const [pattern, replacement] of pack.patterns){
  assert.ok(pattern.startsWith('^') && pattern.endsWith('$'), 'patterns match whole messages');
  assert.ok(new RegExp(pattern) && replacement);
}
console.log('catalog, fallback, placeholders, protected content and reversible display passed');
"""
    result = subprocess.run([node, "-e", script, str(STATIC)], capture_output=True,
                            text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stdout + result.stderr
