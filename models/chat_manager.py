"""
Менеджер чатов для AI тренера
Управляет сохранением, загрузкой и организацией чатов
"""

import json
import os
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from config.settings import Settings

CHAT_ID_RE = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
MAX_TITLE_LENGTH = 120
MAX_PREVIEW_LENGTH = 120


class ChatManager:
    """Управляет чатами AI тренера"""
    
    def __init__(self, chats_dir: Optional[str] = None):
        self.chats_dir = chats_dir or Settings.CHATS_DIR
        self.ensure_chats_directory()
    
    def ensure_chats_directory(self):
        """Создает директорию для чатов если её нет"""
        if not os.path.exists(self.chats_dir):
            os.makedirs(self.chats_dir)

    def _resolve_chat_path(self, chat_id: str) -> str:
        """Validate a chat id and return the safe resolved file path.

        Rejects anything that is not a plain identifier and double-checks that
        the resolved path stays inside the chats directory, so a crafted id
        can never escape the storage root (M2 #266 path-traversal gate).
        """
        if not isinstance(chat_id, str) or not CHAT_ID_RE.match(chat_id):
            raise ValueError("invalid chat id")
        base = os.path.realpath(self.chats_dir)
        path = os.path.realpath(os.path.join(base, f"{chat_id}.json"))
        if os.path.commonpath([base, path]) != base:
            raise ValueError("invalid chat id")
        return path

    @staticmethod
    def _validate_title(title: str) -> str:
        normalized = str(title or "").strip()
        if not normalized:
            raise ValueError("title is empty")
        if len(normalized) > MAX_TITLE_LENGTH:
            raise ValueError("title is too long")
        return normalized
    
    def create_new_chat(self, title: str = None) -> str:
        """Создает новый чат и возвращает его ID"""
        chat_id = str(uuid.uuid4())[:8]  # Короткий ID
        
        if not title:
            title = f"Чат {datetime.now().strftime('%d.%m %H:%M')}"
        
        chat_data = {
            "id": chat_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "messages": []
        }
        
        self.save_chat(chat_id, chat_data)
        return chat_id
    
    def save_chat(self, chat_id: str, chat_data: Dict[str, Any]):
        """Сохраняет чат в файл"""
        chat_data["updated_at"] = datetime.now().isoformat()

        file_path = self._resolve_chat_path(chat_id)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, ensure_ascii=False, indent=2)
    
    def load_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Загружает чат из файла"""
        file_path = self._resolve_chat_path(chat_id)
        
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки чата {chat_id}: {e}")
            return None
    
    def get_chat_list(self, scope: str = "all") -> List[Dict[str, Any]]:
        """Возвращает список чатов, отсортированный по времени обновления.

        ``scope`` is ``all`` (default), ``active``, or ``archive``. Legacy JSON
        files without archive metadata are read as active; their messages are
        never rewritten.
        """
        chats = []
        
        for filename in os.listdir(self.chats_dir):
            if filename.endswith('.json'):
                chat_id = filename[:-5]  # Убираем .json
                chat_data = self.load_chat(chat_id)
                
                if chat_data:
                    archived = bool(chat_data.get("archived", False))
                    if scope == "active" and archived:
                        continue
                    if scope == "archive" and not archived:
                        continue
                    messages = chat_data.get("messages", [])
                    last_content = str(messages[-1].get("content") or "") if messages else ""
                    chats.append({
                        "id": chat_data["id"],
                        "title": chat_data["title"],
                        "created_at": chat_data["created_at"],
                        "updated_at": chat_data["updated_at"],
                        "message_count": len(messages),
                        "archived": archived,
                        "preview": last_content[:MAX_PREVIEW_LENGTH],
                    })
        
        # Сортируем по времени обновления (новые сначала)
        chats.sort(key=lambda x: x["updated_at"], reverse=True)
        return chats
    
    def delete_chat(self, chat_id: str) -> bool:
        """Удаляет чат"""
        file_path = self._resolve_chat_path(chat_id)
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except Exception as e:
                print(f"Ошибка удаления чата {chat_id}: {e}")
                return False
        return False
    
    def clear_chat(self, chat_id: str) -> bool:
        """Очищает все сообщения в чате, сохраняя его структуру"""
        chat_data = self.load_chat(chat_id)
        if chat_data:
            chat_data["messages"] = []
            chat_data["title"] = f"Чат {datetime.now().strftime('%d.%m %H:%M')}"
            self.save_chat(chat_id, chat_data)
            return True
        return False
    
    def update_chat_title(self, chat_id: str, new_title: str) -> bool:
        """Обновляет название чата"""
        normalized = self._validate_title(new_title)
        chat_data = self.load_chat(chat_id)
        if chat_data:
            chat_data["title"] = normalized
            self.save_chat(chat_id, chat_data)
            return True
        return False

    def set_archived(self, chat_id: str, archived: bool) -> bool:
        """Пометить чат архивным (True) или активным (False)."""
        chat_data = self.load_chat(chat_id)
        if chat_data:
            chat_data["archived"] = bool(archived)
            self.save_chat(chat_id, chat_data)
            return True
        return False
    
    def add_message(self, chat_id: str, role: str, content: str) -> bool:
        """Добавляет сообщение в чат"""
        chat_data = self.load_chat(chat_id)
        if not chat_data:
            print(f"[ChatManager] ⚠️ Не удалось загрузить чат {chat_id} для добавления сообщения.")
            return False
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        chat_data["messages"].append(message)
        
        # Автоматически обновляем название чата на основе первого сообщения
        if len(chat_data["messages"]) == 1 and role == "user":
            # Берем первые 50 символов для названия
            auto_title = content[:50] + ("..." if len(content) > 50 else "")
            chat_data["title"] = auto_title
        
        self.save_chat(chat_id, chat_data)
        return True
    
    def get_chat_messages(self, chat_id: str) -> List[Dict[str, Any]]:
        """Возвращает сообщения чата"""
        chat_data = self.load_chat(chat_id)
        if chat_data:
            return chat_data.get("messages", [])
        return []
    
    def export_chat(self, chat_id: str, format_type: str = "text") -> str:
        """Экспортирует чат в текстовом формате"""
        chat_data = self.load_chat(chat_id)
        if not chat_data:
            return ""
        
        if format_type == "text":
            lines = []
            lines.append(f"Чат: {chat_data['title']}")
            lines.append(f"Создан: {chat_data['created_at']}")
            lines.append(f"Обновлен: {chat_data['updated_at']}")
            lines.append("=" * 50)
            lines.append("")
            
            for msg in chat_data.get("messages", []):
                role_name = "🤔 Пользователь" if msg["role"] == "user" else "🤖 AI Тренер"
                lines.append(f"{role_name}: {msg['content']}")
                lines.append("")
            
            return "\n".join(lines)
        
        return ""
    
    def search_chats(self, query: str, scope: str = "all") -> List[Dict[str, Any]]:
        """Поиск по названию и сообщениям в заданном scope."""
        query = (query or "").strip().lower()
        matching_chats = []

        for chat_info in self.get_chat_list(scope=scope):
            chat_data = self.load_chat(chat_info["id"])
            if not chat_data:
                continue

            if not query:
                matching_chats.append(chat_info)
                continue

            # Поиск в названии
            if query in chat_data["title"].lower():
                matching_chats.append(chat_info)
                continue
            
            # Поиск в сообщениях
            for msg in chat_data.get("messages", []):
                if query in msg["content"].lower():
                    matching_chats.append(chat_info)
                    break
        
        return matching_chats
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику по чатам"""
        chats = self.get_chat_list()
        
        total_messages = sum(chat["message_count"] for chat in chats)
        
        if chats:
            latest_chat = max(chats, key=lambda x: x["updated_at"])
            oldest_chat = min(chats, key=lambda x: x["created_at"])
        else:
            latest_chat = oldest_chat = None
        
        return {
            "total_chats": len(chats),
            "total_messages": total_messages,
            "latest_chat": latest_chat,
            "oldest_chat": oldest_chat
        }
