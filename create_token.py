import sys
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/analytics.readonly',
]

def main():
    token_file = sys.argv[1] if len(sys.argv) > 1 else 'token_new.json'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    creds_file = 'credentials.json'

    if not os.path.exists(creds_file):
        print(f'❌ {creds_file} が見つかりません')
        sys.exit(1)

    print(f'ブラウザが開きます。対象のGoogleアカウントでログインしてください。')
    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
    creds = flow.run_local_server(port=port)

    with open(token_file, 'w') as f:
        f.write(creds.to_json())

    print(f'✅ {token_file} を作成しました')

if __name__ == '__main__':
    main()
