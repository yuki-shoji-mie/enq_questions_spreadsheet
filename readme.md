## 依存ライブラリとバージョン

このアプリは Google Apps Script で動作し、外部ライブラリは使用していません。

- **Google Apps Script 組み込みサービス**
  - `SpreadsheetApp`
  - `HtmlService`
  - `DriveApp`
  - `Utilities`
- **ランタイム**
  - V8（Apps Script の標準ランタイム）

## 注意点

- 依存関係は **Google Apps Script の標準サービスのみ** です。
- **npm/pip などのパッケージ管理は不要**です。
- 実行環境は **Google 側で管理されるため、バージョン固定はできません**。
  - Apps Script のアップデートにより挙動が変わる可能性があります。
