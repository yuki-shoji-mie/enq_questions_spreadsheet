/**
 * 定数定義
 */
const SHEET_Q = "Questions";
const SHEET_C = "Choices";
const QKEY_PREFIX = "q";
const QKEY_DIGITS = 5;
const ALLOWED_WRITE_EMAILS = [
  // 例: "you@example.com",
"yuki.shoji@think-mie.co.jp",
"tijuana110@gmail.com"
];
const SAVE_LOCK_TIMEOUT_MS = 10000;

function normalizeQid_(value) {
  return String(value || "")
    .trim()
    .replace(/[－–—]/g, "-")
    .replace(/\s+/g, "");
}

function normalizeType_(value) {
  const v = String(value || "").trim();
  const upper = v.toUpperCase();
  if (upper === "SA") return "single";
  if (upper === "MA") return "multi";
  if (upper === "NA") return "number";
  if (upper === "FA") return "free_answer";
  if (v === "free") return "free_answer";
  return v;
}

function escapeFormulaText_(value) {
  const text = String(value || "");
  if (/^[=+\-@]/.test(text)) return "'" + text;
  return text;
}

function headerIndexMap_(headers) {
  const map = {};
  for (let i = 0; i < headers.length; i++) {
    const key = String(headers[i] || "").trim().toLowerCase();
    if (key) map[key] = i;
  }
  return map;
}

function getChoiceColumn_(map, candidates) {
  for (let i = 0; i < candidates.length; i++) {
    const key = candidates[i].toLowerCase();
    if (key in map) return map[key];
  }
  return -1;
}

function getSheetByNameFlexible_(ss, name) {
  let sheet = ss.getSheetByName(name);
  if (sheet) return sheet;
  const sheets = ss.getSheets();
  const suffix = ` - ${name}`.toLowerCase();
  for (let i = 0; i < sheets.length; i++) {
    const sName = sheets[i].getName();
    if (sName.toLowerCase().endsWith(suffix)) return sheets[i];
  }
  for (let i = 0; i < sheets.length; i++) {
    const sName = sheets[i].getName();
    if (sName.toLowerCase().includes(name.toLowerCase())) return sheets[i];
  }
  throw new Error("エラーが発生しました。管理者に連絡してください。");
}

function assertAuthorizedWrite_() {
  const email = Session.getActiveUser().getEmail();
  if (!email || ALLOWED_WRITE_EMAILS.indexOf(email) === -1) {
    throw new Error("エラーが発生しました。管理者に連絡してください。");
  }
}

/**
 * スプレッドシートが開いたときに実行される
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('設問入力')
    .addItem('サイドバーを開く', 'openSidebar')
    .addSeparator()
    .addItem('YAMLを書き出し(Driveに保存)', 'exportYamlToDrive')
    .addItem('MD+YAMLを書き出し(Driveに保存)', 'exportMdYamlToDrive')
    .addToUi();
}

function createHtmlOutputFlexible_(names) {
  let lastErr = null;
  for (let i = 0; i < names.length; i++) {
    try {
      return HtmlService.createHtmlOutputFromFile(names[i]);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("HTMLファイルが見つかりません。");
}

/**
 * サイドバーを表示
 */
function openSidebar() {
  const html = createHtmlOutputFlexible_(['sidebar_copy', 'Sidebar', 'sidebar'])
    .setTitle('設問入力フォーム')
    .setWidth(400);
  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * 設問詳細の取得（既存設問読込用）
 */
function apiGetQuestionDetail(qid) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheetQ = getSheetByNameFlexible_(ss, SHEET_Q);
    const sheetC = getSheetByNameFlexible_(ss, SHEET_C);

    const dataQ = sheetQ.getDataRange().getValues();
    if (!dataQ || dataQ.length === 0) {
      throw new Error("エラーが発生しました。管理者に連絡してください。");
    }
    const headersQ = dataQ[0];

    // カラム位置を特定（qid を優先）
    let idxQid = headersQ.indexOf("qid");
    if (idxQid === -1) idxQid = headersQ.indexOf("display_id");
    if (idxQid === -1) idxQid = 1; // 見つからない場合はB列と仮定

    const idxQkey = headersQ.indexOf("qkey") === -1 ? 0 : headersQ.indexOf("qkey");
    const normalizedQid = normalizeQid_(qid);

    let questionData = null;
    let safeQuestionData = null;

    // 検索
    for (let i = 1; i < dataQ.length; i++) {
      if (normalizeQid_(dataQ[i][idxQid]) === normalizedQid) {
        questionData = {};
        safeQuestionData = {};
        headersQ.forEach((header, index) => {
          let rawVal = dataQ[i][index];
          if (header === "type") rawVal = normalizeType_(rawVal);
          questionData[header] = rawVal;
          safeQuestionData[header] = (rawVal === null || rawVal === undefined) ? "" : String(rawVal);
        });
        break;
      }
    }

    if (!questionData) {
      throw new Error("エラーが発生しました。管理者に連絡してください。");
    }

    // Choicesシートから選択肢を取得
    const qkey = String((questionData && questionData.qkey) || dataQ[0][idxQkey] || "").trim();
    const qkeyLower = qkey.toLowerCase();
    const dataC = sheetC.getDataRange().getValues();
    const headersC = dataC[0] || [];
    const mapC = headerIndexMap_(headersC);
    const idxCKey = getChoiceColumn_(mapC, ["qkey"]);
    const idxCLabel = getChoiceColumn_(mapC, ["choice_label", "choices_label", "label"]);
    const idxCValue = getChoiceColumn_(mapC, ["choice_value", "choices_value", "value"]);
    let choicesText = "";
    for (let i = 1; i < dataC.length; i++) {
      const rowKey = idxCKey >= 0 ? dataC[i][idxCKey] : dataC[i][0];
      if (String(rowKey).trim().toLowerCase() === qkeyLower) {
        const label = idxCLabel >= 0 ? dataC[i][idxCLabel] : "";
        const value = idxCValue >= 0 ? dataC[i][idxCValue] : "";
        const text = String(label || value || "").trim();
        if (text) choicesText += text + "\n";
      }
    }

    return {
      question: safeQuestionData || {},
      choices_text: choicesText.trim()
    };
  } catch (e) {
    return {
      error: true,
      message: "エラーが発生しました。管理者に連絡してください。"
    };
  }
}

/**
 * 設問の保存（新規追加・更新）
 */
function saveQuestion(payload) {
  assertAuthorizedWrite_();
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(SAVE_LOCK_TIMEOUT_MS);
  } catch (e) {
    throw new Error("エラーが発生しました。管理者に連絡してください。");
  }
  try {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetQ = getSheetByNameFlexible_(ss, SHEET_Q);
  const sheetC = getSheetByNameFlexible_(ss, SHEET_C);
  
  let qkey = String(payload.qkey || "").trim();
  const isNew = (!qkey || qkey === "" || qkey === "新規" || qkey === "undefined");

  if (isNew) {
    const lastRowQ = sheetQ.getLastRow();
    let maxNum = 0;
    if (lastRowQ > 1) {
      const allQkeys = sheetQ.getRange(2, 1, lastRowQ - 1, 1).getValues();
      allQkeys.forEach(row => {
        const m = String(row[0]).match(/[qQ](\d+)/);
        if (m) {
          const num = parseInt(m[1], 10);
          if (num > maxNum) maxNum = num;
        }
      });
    }
    qkey = QKEY_PREFIX + String(maxNum + 1).padStart(QKEY_DIGITS, '0');
  }

  const dataQ = sheetQ.getDataRange().getValues();
  let rowIdxQ = -1;
  if (!isNew) {
    for (let i = 1; i < dataQ.length; i++) {
      if (String(dataQ[i][0]).trim() === qkey) {
        rowIdxQ = i + 1;
        break;
      }
    }
  }

  const nowStr = Utilities.formatDate(new Date(), "JST", "yyyy-MM-dd HH:mm:ss");
  
  // カラム名に合わせてマッピング
  const rowDataQ = [
    qkey,
    escapeFormulaText_(payload.qid || ""),
    Number(payload.q_level) || 2,
    escapeFormulaText_(payload.parent_qkey || ""),
    Number(payload.order) || 0,
    escapeFormulaText_(payload.type || "single"),
    escapeFormulaText_(payload.question || ""),
    escapeFormulaText_(payload.instruction || ""),
    Number(payload.required) === 1 ? 1 : 0,
    escapeFormulaText_(payload.show_if || ""),
    escapeFormulaText_(payload.var_name || ""),
    escapeFormulaText_(payload.tags || ""),
    escapeFormulaText_(payload.note || ""),
    escapeFormulaText_(payload.status || "draft"),
    nowStr
  ];

  if (rowIdxQ > 0) {
    sheetQ.getRange(rowIdxQ, 1, 1, rowDataQ.length).setValues([rowDataQ]);
  } else {
    sheetQ.appendRow(rowDataQ);
  }

  // Choices更新
  const lastRowC = sheetC.getLastRow();
  if (lastRowC > 1) {
    const dataC = sheetC.getRange(1, 1, lastRowC, sheetC.getLastColumn()).getValues();
    const headersC = dataC[0] || [];
    const mapC = headerIndexMap_(headersC);
    const idxCKey = getChoiceColumn_(mapC, ["qkey"]);
    for (let i = dataC.length - 1; i >= 1; i--) {
      const rowKey = idxCKey >= 0 ? dataC[i][idxCKey] : dataC[i][0];
      if (String(rowKey).trim() === qkey) {
        sheetC.deleteRow(i + 1);
      }
    }
  }

  if (payload.choices_text) {
    const headersC = sheetC.getRange(1, 1, 1, sheetC.getLastColumn()).getValues()[0] || [];
    const mapC = headerIndexMap_(headersC);
    const idxCKey = getChoiceColumn_(mapC, ["qkey"]);
    const idxCQid = getChoiceColumn_(mapC, ["qid"]);
    const idxCNo = getChoiceColumn_(mapC, ["choice_no", "choices_no", "no"]);
    const idxCValue = getChoiceColumn_(mapC, ["choice_value", "choices_value", "value"]);
    const idxCLabel = getChoiceColumn_(mapC, ["choice_label", "choices_label", "label"]);
    const idxCOther = getChoiceColumn_(mapC, ["is_other", "other"]);

    const lines = payload.choices_text.split(/\n/).filter(l => l.trim() !== "");
    lines.forEach((line, idx) => {
      let label = line.trim();
      if (label.includes(":") || label.includes("：")) {
        const sep = label.includes(":") ? ":" : "：";
        label = label.split(sep).slice(1).join(sep).trim();
      }
      label = escapeFormulaText_(label);
      const choiceNo = String(idx + 1);
      const choiceValue = choiceNo;
      const row = new Array(headersC.length).fill("");
      if (idxCKey >= 0) row[idxCKey] = qkey;
      if (idxCQid >= 0) row[idxCQid] = payload.qid || "";
      if (idxCNo >= 0) row[idxCNo] = choiceNo;
      if (idxCValue >= 0) row[idxCValue] = choiceValue;
      if (idxCLabel >= 0) row[idxCLabel] = label;
      if (idxCOther >= 0) row[idxCOther] = 0;
      if (headersC.length > 0) {
        sheetC.appendRow(row);
      } else {
        sheetC.appendRow([qkey, payload.qid || "", choiceNo, choiceValue, label]);
      }
    });
  }

  return { ok: true, qkey: qkey };
  } finally {
    try {
      lock.releaseLock();
    } catch (e) {
      // ignore
    }
  }
}

// --- 以下、書き出し用ダミー関数（実装が必要な場合は追加してください） ---
function exportYamlToDrive() { SpreadsheetApp.getUi().alert("YAML出力機能は未実装です。"); }

function ping() {
  return Utilities.formatDate(new Date(), "JST", "yyyy-MM-dd HH:mm:ss");
}

function exportMdYamlToDrive() {
  assertAuthorizedWrite_();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetQ = getSheetByNameFlexible_(ss, SHEET_Q);
  const sheetC = getSheetByNameFlexible_(ss, SHEET_C);

  const dataQ = sheetQ.getDataRange().getValues();
  const headersQ = dataQ[0];

  const dataC = sheetC.getDataRange().getValues();
  const headersC = dataC[0] || [];
  const mapC = headerIndexMap_(headersC);
  const idxCKey = getChoiceColumn_(mapC, ["qkey"]);
  const idxCValue = getChoiceColumn_(mapC, ["choice_value", "choices_value", "value"]);
  const idxCLabel = getChoiceColumn_(mapC, ["choice_label", "choices_label", "label"]);
  const choicesMap = {};
  for (let i = 1; i < dataC.length; i++) {
    const qkey = String((idxCKey >= 0 ? dataC[i][idxCKey] : dataC[i][0]) || "").trim();
    if (!qkey) continue;
    if (!choicesMap[qkey]) choicesMap[qkey] = [];
    const value = String((idxCValue >= 0 ? dataC[i][idxCValue] : "") || "").trim();
    const label = String((idxCLabel >= 0 ? dataC[i][idxCLabel] : "") || "").trim();
    if (value || label) choicesMap[qkey].push({ value, label });
  }

  const lines = [];
  for (let i = 1; i < dataQ.length; i++) {
    const row = dataQ[i];
    const q = {};
    headersQ.forEach((header, idx) => {
      q[header] = row[idx];
    });

    const qkey = String(q.qkey || "").trim();
    if (!qkey) continue;

    const qid = String(q.qid || q.display_id || "").trim();
    const question = String(q.question || "").trim();
    const level = q.q_level || "";
    const type = String(q.type || "").trim();

    lines.push(`# ${qid} ${question}`.trim());
    lines.push("```yaml");
    lines.push(`id: ${qkey}`);
    lines.push(`qid: ${qid}`);
    lines.push(`level: ${level}`);
    lines.push(`type: ${type}`);
    lines.push("choices:");

    const choices = choicesMap[qkey] || [];
    if (choices.length === 0) {
      lines.push(`  "1": ""`);
    } else {
      choices.forEach(choice => {
        lines.push(`  "${choice.value}": "${choice.label}"`);
      });
    }
    lines.push("```");
    lines.push("");
  }

  const content = lines.join("\n");
  const filename = `questions_${Utilities.formatDate(new Date(), "JST", "yyyyMMdd_HHmmss")}.md`;
  DriveApp.createFile(filename, content, MimeType.PLAIN_TEXT);
  SpreadsheetApp.getUi().alert("MD+YAMLを書き出しました: " + filename);
}