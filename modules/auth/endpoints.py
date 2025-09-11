"""
Authentication API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from modules.auth.service import auth_service
from modules.config.settings import settings
import json

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/signup")
async def signup(
    firstname: str = Form(...), 
    lastname: str = Form(...),
    email: str = Form(...), 
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    """
    User signup endpoint with email validation and password confirmation
    """
    return auth_service.signup_user(firstname, lastname, email, password, confirm_password)

@router.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    """
    User login endpoint using email and password
    """
    return auth_service.login_user(email, password)

@router.post("/google-signup")
async def google_signup(id_token: str = Form(...)):
    """
    Google OAuth signup endpoint
    Accepts FormData with id_token field
    """
    if not id_token:
        raise HTTPException(status_code=400, detail="id_token is required")
    
    return auth_service.google_signup(id_token)

@router.post("/google-signin")
async def google_signin(id_token: str = Form(...)):
    """
    Google OAuth signin endpoint
    Accepts FormData with id_token field
    """
    if not id_token:
        raise HTTPException(status_code=400, detail="id_token is required")
    
    return auth_service.google_signin(id_token)

@router.post("/google-signup-userinfo")
async def google_signup_userinfo(
    email: str = Form(...),
    firstname: str = Form(...),
    lastname: str = Form(...),
    google_id: str = Form(...)
):
    """
    Google OAuth signup endpoint using user info instead of ID token
    """
    return auth_service.google_signup_userinfo(email, firstname, lastname, google_id)

@router.post("/google-signin-userinfo")
async def google_signin_userinfo(
    email: str = Form(...),
    google_id: str = Form(...)
):
    """
    Google OAuth signin endpoint using user info instead of ID token
    """
    return auth_service.google_signin_userinfo(email, google_id)

@router.get("/google-oauth-test", response_class=HTMLResponse)
async def google_oauth_test():
    """
    Test page for Google OAuth integration
    This provides a simple form to test Google OAuth
    """
    google_client_id = settings.GOOGLE_CLIENT_ID
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Google OAuth Test</title>
    <script src="https://accounts.google.com/gsi/client" async defer></script>
</head>
<body>
    <h1>Google OAuth Test</h1>
    
    <h2>Configuration Status:</h2>
    <p>Google Client ID: {'✅ Configured' if google_client_id else '❌ Not configured'}</p>
    <p>Client ID (partial): {google_client_id[:20] + '...' if google_client_id else 'None'}</p>
    
    <h2>Google Sign-In Test:</h2>
    <div id="g_id_onload"
         data-client_id="{google_client_id}"
         data-callback="handleCredentialResponse">
    </div>
    <div class="g_id_signin" data-type="standard"></div>
    
    <h2>Manual Test:</h2>
    <form id="manual-form" action="/auth/google-signup" method="post">
        <label for="id_token">ID Token:</label><br>
        <textarea id="id_token" name="id_token" rows="10" cols="80" placeholder="Paste Google ID token here..."></textarea><br><br>
        <input type="submit" value="Test Google Signup">
    </form>
    
    <h2>Instructions:</h2>
    <ol>
        <li>Make sure your Google Client ID is configured in .env</li>
        <li>You need to add this domain to your Google OAuth configuration</li>
        <li>Authorized redirect URIs should include: http://localhost:8000</li>
        <li>Click the Google Sign-In button above to get an ID token</li>
        <li>Or manually paste an ID token in the form below</li>
    </ol>
    
    <script>
    function handleCredentialResponse(response) {{
        console.log("Encoded JWT ID token: " + response.credential);
        document.getElementById('id_token').value = response.credential;
        alert('ID token received! Check the textarea below or console.');
    }}
    
    // Handle form submission
    document.getElementById('manual-form').addEventListener('submit', function(e) {{
        e.preventDefault();
        const token = document.getElementById('id_token').value;
        if (!token) {{
            alert('Please enter an ID token');
            return;
        }}
        
        // Submit via fetch to see the response
        fetch('/auth/google-signup', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded',
            }},
            body: 'id_token=' + encodeURIComponent(token)
        }})
        .then(response => response.json())
        .then(data => {{
            alert('Response: ' + JSON.stringify(data, null, 2));
            console.log('Response:', data);
        }})
        .catch(error => {{
            alert('Error: ' + error);
            console.error('Error:', error);
        }});
    }});
    </script>
</body>
</html>
    """
    return html_content

@router.get("/google-config-check")
async def google_config_check():
    """
    Check Google OAuth configuration status
    """
    return {
        "google_client_id_configured": bool(settings.GOOGLE_CLIENT_ID),
        "google_client_id_preview": settings.GOOGLE_CLIENT_ID[:20] + "..." if settings.GOOGLE_CLIENT_ID else None,
        "instructions": [
            "1. Make sure GOOGLE_CLIENT_ID is set in your .env file",
            "2. Get a valid Google ID token from the OAuth flow",
            "3. The token should be a JWT (starts with 'eyJ')",
            "4. Use the /auth/google-oauth-test endpoint to test"
        ]
    }

@router.post("/debug-request")
async def debug_request(request: Request):
    """
    Debug endpoint to see exactly what Postman is sending
    """
    try:
        body = await request.body()
        headers = dict(request.headers)
        
        # Try to parse as different formats
        parsed_data = {}
        
        try:
            if body:
                body_str = body.decode('utf-8')
                parsed_data['raw_body'] = body_str
                
                # Try JSON
                try:
                    parsed_data['json_parsed'] = json.loads(body_str)
                except:
                    parsed_data['json_parsed'] = "Not valid JSON"
                
                # Try form data
                if "=" in body_str:
                    form_data = {}
                    for pair in body_str.split("&"):
                        if "=" in pair:
                            key, value = pair.split("=", 1)
                            import urllib.parse
                            form_data[urllib.parse.unquote(key)] = urllib.parse.unquote(value)
                    parsed_data['form_parsed'] = form_data
        except Exception as e:
            parsed_data['parse_error'] = str(e)
        
        return {
            "method": request.method,
            "url": str(request.url),
            "headers": headers,
            "content_type": headers.get('content-type', 'None'),
            "body_length": len(body) if body else 0,
            "parsed_data": parsed_data
        }
    except Exception as e:
        return {"error": str(e)}