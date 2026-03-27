from app.utils.auth import get_current_user
from app.utils.auth import require_role

# Legacy standalone admin verification kept for future reference:
# from fastapi import HTTPException, Depends
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# import os
# from dotenv import load_dotenv
#
# load_dotenv()
# reusable_oauth2 = HTTPBearer()
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
#
# def _get_supabase_client():
#     ...
#
# async def verify_admin(authorization: HTTPAuthorizationCredentials = Depends(reusable_oauth2)):
#     ...


verify_admin = require_role("admin")
