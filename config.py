# config.py — サイトリストと設定

SITES = [
    {
        "name": "ヒューマンワーク",
        "property": "https://www.human-work.co.jp/",
        "sheet_id": "1ydh6ElguVth-XAvgPd7aXYE520TLxOsqHt6Hf0XCRiQ",
        "drive_folder": "ヒューマンワーク",
    },
    {
        "name": "Revcomm",
        "property": "https://miitel.com/jp/",
        "sheet_id": "1pedLEQmAqNNl2CHz4unkMlaFj8ulQ8sP2aTvLvb3e-o",
        "drive_folder": "Revcomm",
    },
    {
        "name": "レンタルPCネット",
        "property": "sc-domain:rental-pc.net",
        "sheet_id": "1suD-xKIfaFE7zS86T30ewFEqWwBixtm5kZtEeqSdK_o",
        "drive_folder": "レンタルPCネット",
    },
    {
        "name": "田所商店",
        "property": "https://misoya.net/",
        "sheet_id": "1gLWa4J6WO1QhHZE5U_0D5YKj1LA4PLV6C4obxJBvX64",
        "drive_folder": "田所商店",
    },
    {
        "name": "みらいワークス",
        "property": "sc-domain:mirai-works.co.jp",
        "sheet_id": "1vNCvJ3yvPVq035O3WImQ0z21OmjRhUlA6exzNxMcol0",
        "drive_folder": "みらいワークス",
    },
    {
        "name": "ラビット探偵社",
        "property": "https://rabbit-tantei.com/",
        "sheet_id": "1F9eCIRDWjzc6S-yzJBR5vhomDDO6bc6H_JTyBhXWRjQ",
        "drive_folder": "ラビット探偵社",
        "token_file": "token_002.json",
    },
    {
        "name": "クルーズプラネット",
        "property": "https://www.cruiseplanet.co.jp/",
        "sheet_id": "16bJ5tCD9G3seOp3NqUaBd0HyNt0LEupgkXBFvtZIgoA",
        "drive_folder": "クルーズプラネット",
        "token_file": "token_002.json",
    },
    {
        "name": "3大セキュリティ",
        "property": "https://group.gmo/",
        "page_filter": "https://group.gmo/security/",
        "sheet_id": "1Zl8n4_3ZG6PA1JdSNWDeENv9hbFkjk1HA26OZnvpLzs",
        "drive_folder": "3大セキュリティ",
        "token_file": "token_003.json",
    },
    {
        "name": "起業の窓口",
        "property": "https://kigyo.gmo/",
        "sheet_id": "1yAWn7T59l9nlKnmtg-OdxiXZdUt2SHyhCzpG63g1D0w",
        "drive_folder": "起業の窓口",
    },
    {
        "name": "中央住宅",
        "property": "https://www.polus-kodate.com/",
        "sheet_id": "1XVjV1e-YNDdefZRXLsSzTpwkTGlxEScMh1Av2ktdBrU",
        "drive_folder": "中央住宅",
        "token_file": "token_005.json",
    },
    {
        "name": "表参道デンタルクリニック",
        "property": "https://www.omotesando-dc.com/",
        "sheet_id": "1_hioaVQP-WsT36TcH4b_mTlprRD8lhODMX01VyoU3xU",
        "drive_folder": "表参道デンタルクリニック",
        "token_file": "token_006.json",
    },
    {
        "name": "東京スタートアップ法律事務所",
        "property": "https://tokyo-startup-law.or.jp/",
        "sheet_id": "",
        "drive_folder": "東京スタートアップ法律事務所",
    },
]

# 認証ファイルのパス（変更不要）
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

# レポートの設定
WEEKS_TO_COMPARE = 5
ROW_LIMIT = 100

# Google DriveのルートフォルダID
DRIVE_ROOT_FOLDER_NAME = "GSCレポート"

# GA4スプシID
GA4_SHEET_ID = '1lm528gFXQ3CzSRAsTYnJpSmz1gPbATueIxlwEM9DdN0'
