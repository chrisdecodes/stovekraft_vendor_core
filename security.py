
from cryptography.fernet import Fernet
from config import settings

class EncryptionManager:
    def __init__(self):
        self.fernet = Fernet(settings.ENCRYPTION_KEY.encode())

    def encrypt(self, data: str) -> str:
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        return self.fernet.decrypt(encrypted_data.encode()).decode()

encryption_manager = EncryptionManager()
