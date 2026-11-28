import msal
import requests
import json
import os

# ==========================================
# CONFIGURATION
# ==========================================
TENANT_ID = '8240a393-7a9f-4a79-8023-0c3b09a1bf2a'
CLIENT_ID = 'c257f12b-331b-4b6c-8889-4c154994890c'
TOKEN_CACHE_FILE = 'm365_token.json'

SCOPES = ["Mail.Send"]
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Put the email address where you want to receive this test:
RECIPIENT_EMAIL = 'bp_1970@hotmail.com'  # <-- Change this to your test recipient


# ==========================================
# AUTHENTICATION (Interactive 1st time, silent after)
# ==========================================
def get_token():
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, 'r') as f:
            cache.deserialize(f.read())

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache
    )

    # Try silent login with cached token
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]

    # First-time setup: Device Code Flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    print("\n" + "="*60)
    print("ONE-TIME SETUP REQUIRED:")
    print(flow["message"])
    print("="*60 + "\n")

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        with open(TOKEN_CACHE_FILE, 'w') as f:
            f.write(cache.serialize())
        return result["access_token"]
    else:
        raise Exception(f"Login failed: {result}")


# ==========================================
# SEND EMAIL TEST
# ==========================================
def send_test_email():
    token = get_token()
    print("✓ Successfully authenticated to Microsoft 365.")

    endpoint = "https://graph.microsoft.com/v1.0/me/sendMail"

    # Minimal valid 1-page blank PDF (base64)
    dummy_pdf_base64 = "JVBERi0xLjQKJcTl8uXrp/Og0MTGCjEgMCBvYmoKPDwKL1R5cGUgL0NhdGFsb2cKL1BhZ2VzIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9UeXBlIC9QYWdlcwovS2lkcyBbMyAwIFJdCi9Db3VudCAxCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9QYWdlCi9QYXJlbnQgMiAwIFIKL01lZGlhQm94IFswIDAgNjEyIDc5Ml0KPj4KZW5kb2JqCnhyZWYKMCA0CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxOCAwMDAwMCBuIAowMDAwMDAwMDY4IDAwMDAwIG4gCjAwMDAwMDAxMjQgMDAwMDAgbiAKdHJhaWxlcgo8PAovU2l6ZSA0Ci9Sb290IDEgMCBSCj4+CnN0YXJ0eHJlZgoxODMKJSVFT0Y="

    html_body = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }
            .container { max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; }
            .header { background: #1e293b; padding: 20px; text-align: center; color: #ffffff; }
            .content { padding: 30px 24px; color: #334155; line-height: 1.6; }
            .btn-table { width: 100%; margin: 24px 0; border-collapse: separate; border-spacing: 12px; }
            .btn { display: block; text-align: center; padding: 12px 18px; font-weight: 600; text-decoration: none; border-radius: 6px; font-size: 15px; }
            .btn-confirm { background-color: #16a34a; color: #ffffff !important; }
            .btn-amend { background-color: #ea580c; color: #ffffff !important; }
            .footer { padding: 14px; background: #f1f5f9; text-align: center; font-size: 12px; color: #64748b; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2 style="margin: 0; font-size: 18px;">PAYG Onboarding Submission</h2>
            </div>
            <div class="content">
                <p>Hello,</p>
                <p>Your PAYG onboarding submission has been generated. Please review the attached summary PDF and confirm your selection below:</p>
                
                <table class="btn-table">
                    <tr>
                        <td style="width: 50%;">
                            <a href="https://example.com/confirm?id=test_123" class="btn btn-confirm">
                                ✓ Confirm Details
                            </a>
                        </td>
                        <td style="width: 50%;">
                            <a href="https://example.com/amend?id=test_123" class="btn btn-amend">
                                ✎ Request Changes
                            </a>
                        </td>
                    </tr>
                </table>

                <p style="font-size: 13px; color: #64748b;">
                    If you have any questions, you can reply directly to this email.
                </p>
            </div>
            <div class="footer">
                Payroll Operations Team &bull; Powered by Odoo
            </div>
        </div>
    </body>
    </html>
    """

    payload = {
        "message": {
            "subject": "ACTION REQUIRED: PAYG Onboarding Confirmation (Test)",
            "body": {
                "contentType": "HTML",
                "content": html_body
            },
            "toRecipients": [
                {"emailAddress": {"address": RECIPIENT_EMAIL}}
            ],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "PAYG_Submission_Summary.pdf",
                    "contentType": "application/pdf",
                    "contentBytes": dummy_pdf_base64
                }
            ]
        },
        "saveToSentItems": "true"
    }

    print(f"Sending test email to {RECIPIENT_EMAIL}...")
    res = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload
    )

    if res.status_code == 202:
        print("✓ SUCCESS! Email sent. Check your inbox and your Outlook Sent folder!")
    else:
        print(f"✗ Failed (Status {res.status_code}): {res.text}")

if __name__ == '__main__':
    send_test_email()
