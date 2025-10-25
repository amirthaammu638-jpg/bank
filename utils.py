from functools import wraps
from flask import make_response, Response
from .models import Account, db
import random
import base64
import cv2
import numpy as np
from googletrans import Translator

# ----------------- CACHE CONTROL ----------------- #
def nocache(view) -> callable:
    @wraps(view)
    def no_cache(*args, **kwargs) -> Response:
        response = make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    return no_cache

# ----------------- ACCOUNT ----------------- #
def get_or_create_account(user):
    if not user.account:
        account_number = "SB" + str(random.randint(10000000, 99999999))
        account = Account(user_id=user.id, account_number=account_number, balance=0.0)
        db.session.add(account)
        db.session.commit()
        db.session.refresh(user)  # ensures user.account is updated
        return account
    return user.account

# ----------------- FACE ENCODING ----------------- #
def get_face_encoding_from_base64(data_url):
    """
    Convert base64 image to a simple OpenCV-based face encoding.
    Returns a flattened grayscale image array (100x100) as encoding.
    """
    try:
        if ',' in data_url:
            _, encoded = data_url.split(',', 1)
        else:
            encoded = data_url

        img_bytes = base64.b64decode(encoded)
        img_array = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Simple encoding: grayscale + resize + flatten
        gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
        resized = cv2.resize(gray, (100, 100))
        encoding = resized.flatten() / 255.0
        return encoding
    except Exception as e:
        print("Face encoding error:", e)
        return None

# ----------------- TRANSLATION ----------------- #
translator = Translator()

def auto_translate(text, target_lang='ml'):  # Malayalam by default
    try:
        result = translator.translate(text, dest=target_lang)
        return result.text
    except Exception:
        return text





