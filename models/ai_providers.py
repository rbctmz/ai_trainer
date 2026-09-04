"""
Универсальная система AI провайдеров для коучинга
Поддерживает: OpenAI, Anthropic, Google Gemini, Ollama, Mock (для тестирования)
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Mapping, Type
import os
from config.settings import Settings

# Консервативный runtime default для Google/gRPC stack в локальном окружении.
os.environ.setdefault('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', 'python')


class AIProvider(ABC):
    """Базовый класс для всех AI провайдеров"""
    
    @abstractmethod
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        """Генерация ответа от AI"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Проверка доступности провайдера"""
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Получить название используемой модели"""
        pass
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Тестирование подключения к провайдеру
        Возвращает словарь с результатами теста
        """
        return {
            'success': False,
            'error': 'Метод test_connection не реализован'
        }
    
    def get_available_models(self) -> List[str]:
        """
        Получить список доступных моделей
        Возвращает список строк с названиями моделей
        """
        return []

    def supports_native_tools(self) -> bool:
        """Умеет ли провайдер нативный function calling (Issue #190).

        Capability класса, не доступности: ключ/клиент проверяются отдельно
        через is_available(). Провайдеры без поддержки остаются на маркерном
        пути [TOOL: ...].
        """
        return False

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        """Нативный вызов с инструментами (Issue #190).

        ``messages`` — OpenAI-стиль список ролей user/assistant/tool;
        ``tools`` — схемы из ``AITools.get_tool_schemas``. Нормализованный
        ответ: ``{"text": str, "tool_calls": [{"id", "name", "arguments"}]}``,
        где ``arguments`` — уже распарсенный dict, никогда SDK-объект или
        JSON-строка.
        """
        raise NotImplementedError(
            f"{type(self).__name__} не поддерживает нативный function calling"
        )


def _native_tool_calls_from_openai_message(message: Any) -> List[Dict[str, Any]]:
    """Normalize OpenAI-style ``message.tool_calls`` into the shared shape."""
    normalized: List[Dict[str, Any]] = []
    for call in list(getattr(message, "tool_calls", None) or []):
        function = getattr(call, "function", None)
        raw_arguments = getattr(function, "arguments", "") if function else ""
        try:
            arguments = json.loads(raw_arguments) if raw_arguments else {}
        except (TypeError, ValueError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        normalized.append(
            {
                "id": str(getattr(call, "id", "") or ""),
                "name": str(getattr(function, "name", "") or "") if function else "",
                "arguments": arguments,
            }
        )
    return normalized


class OpenAICompatibleToolsMixin:
    """Общий адаптер tools API для OpenAI-совместимых клиентов (OpenAI, DeepSeek)."""

    def supports_native_tools(self) -> bool:
        return True

    @staticmethod
    def _messages_for_chat_completions(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Перевести tool-вызовы рантайма в wire-формат chat.completions."""
        translated: List[Dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "")
            tool_calls = message.get("tool_calls")
            if role == "assistant" and tool_calls:
                wire_calls: List[Dict[str, Any]] = []
                for call in tool_calls:
                    if not isinstance(call, Mapping):
                        continue
                    arguments = call.get("arguments") or {}
                    if not isinstance(arguments, dict):
                        arguments = {}
                    wire_calls.append(
                        {
                            "id": str(call.get("id") or ""),
                            "type": "function",
                            "function": {
                                "name": str(call.get("name") or ""),
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    )
                translated.append(
                    {
                        "role": "assistant",
                        "content": str(message.get("content") or ""),
                        "tool_calls": wire_calls,
                    }
                )
                continue

            if role == "tool":
                translated.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(message.get("tool_call_id") or ""),
                        "content": str(message.get("content") or ""),
                    }
                )
                continue

            translated.append(dict(message))
        return translated

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        if not getattr(self, "client", None):
            return {"text": f"{type(self).__name__}: клиент не настроен", "tool_calls": []}

        full_messages: List[Dict[str, Any]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(self._messages_for_chat_completions(messages))

        request: Dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "max_tokens": self.settings.AI_RESPONSE_MAX_TOKENS,
            # Tool selection/arguments must be deterministic (issue #440).
            "temperature": self.settings.AI_TOOLS_TEMPERATURE,
        }
        payload = [
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            }
            for schema in tools or []
        ]
        if payload:
            request["tools"] = payload

        try:
            response = self.client.chat.completions.create(**request)
        except Exception as exc:
            return {"text": f"Ошибка {type(self).__name__}: {exc}", "tool_calls": []}

        message = response.choices[0].message
        return {
            "text": str(getattr(message, "content", None) or ""),
            "tool_calls": _native_tool_calls_from_openai_message(message),
        }


class OpenAIProvider(OpenAICompatibleToolsMixin, AIProvider):
    """Провайдер OpenAI (GPT-3.5/GPT-4)"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.client = None
        
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                print("OpenAI библиотека не установлена")
            except Exception as e:
                print(f"Ошибка инициализации OpenAI: {e}")
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "OpenAI провайдер не настроен"
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.settings.AI_RESPONSE_MAX_TOKENS,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Ошибка OpenAI: {e}"
    
    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None
    
    def get_model_name(self) -> str:
        return f"OpenAI {self.model}"
    
    def test_connection(self) -> Dict[str, Any]:
        """Тестирование подключения к OpenAI"""
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте API ключ.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'response_length': len(response.choices[0].message.content)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей OpenAI"""
        if not self.client:
            return []
        
        try:
            models = self.client.models.list()
            # Фильтруем только GPT модели
            gpt_models = [
                model.id for model in models.data 
                if 'gpt' in model.id.lower() and 'instruct' not in model.id.lower()
            ]
            return sorted(gpt_models)
        except Exception as e:
            print(f"Ошибка получения моделей OpenAI: {e}")
            return ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]  # Fallback список


class AnthropicProvider(AIProvider):
    """Провайдер Anthropic (Claude)"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.ANTHROPIC_MODEL
        self.client = None
        
        if self.api_key:
            try:
                from anthropic import Anthropic
                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                print("Anthropic библиотека не установлена")
            except Exception as e:
                print(f"Ошибка инициализации Anthropic: {e}")
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "Anthropic провайдер не настроен"
        
        try:
            messages = [{"role": "user", "content": prompt}]
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.settings.AI_RESPONSE_MAX_TOKENS,
                temperature=0.7,
                system=system_prompt if system_prompt else None,
                messages=messages
            )
            
            # Claude возвращает список блоков контента
            return response.content[0].text if response.content else ""

        except Exception as e:
            return f"Ошибка Anthropic: {e}"

    def supports_native_tools(self) -> bool:
        return True

    @staticmethod
    def _messages_for_tool_use(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OpenAI-стиль истории → Anthropic messages.

        assistant с tool_calls становится content-блоками tool_use;
        подряд идущие tool-результаты сворачиваются в ОДИН user-ход с
        tool_result-блоками (Anthropic требует их сразу после tool_use).
        """
        translated: List[Dict[str, Any]] = []
        pending_results: List[Dict[str, Any]] = []

        def _flush_results() -> None:
            if pending_results:
                translated.append({"role": "user", "content": list(pending_results)})
                pending_results.clear()

        for message in messages:
            role = str(message.get("role") or "")
            if role == "tool":
                pending_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": str(message.get("tool_call_id") or ""),
                        "content": str(message.get("content") or ""),
                    }
                )
                continue
            _flush_results()
            if role == "assistant" and message.get("tool_calls"):
                content: List[Dict[str, Any]] = []
                text = str(message.get("content") or "")
                if text:
                    content.append({"type": "text", "text": text})
                for call in message["tool_calls"]:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": str(call.get("id") or ""),
                            "name": str(call.get("name") or ""),
                            "input": dict(call.get("arguments") or {}),
                        }
                    )
                translated.append({"role": "assistant", "content": content})
            elif role in {"user", "assistant"}:
                translated.append({"role": role, "content": message.get("content") or ""})
        _flush_results()
        return translated

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        if not self.client:
            return {"text": "Anthropic провайдер не настроен", "tool_calls": []}

        request: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.settings.AI_RESPONSE_MAX_TOKENS,
            "temperature": 0.7,
            "messages": self._messages_for_tool_use(messages),
        }
        if system_prompt:
            request["system"] = system_prompt
        if tools:
            request["tools"] = [
                {
                    "name": schema["name"],
                    "description": schema["description"],
                    "input_schema": schema["parameters"],
                }
                for schema in tools
            ]

        try:
            response = self.client.messages.create(**request)
        except Exception as exc:
            return {"text": f"Ошибка Anthropic: {exc}", "tool_calls": []}

        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for block in list(getattr(response, "content", None) or []):
            block_type = str(getattr(block, "type", "") or "")
            if block_type == "text":
                text_parts.append(str(getattr(block, "text", "") or ""))
            elif block_type == "tool_use":
                raw_input = getattr(block, "input", None)
                tool_calls.append(
                    {
                        "id": str(getattr(block, "id", "") or ""),
                        "name": str(getattr(block, "name", "") or ""),
                        "arguments": dict(raw_input) if isinstance(raw_input, dict) else {},
                    }
                )
        return {"text": "\n".join(part for part in text_parts if part), "tool_calls": tool_calls}

    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None
    
    def get_model_name(self) -> str:
        return f"Anthropic {self.model}"
    
    def test_connection(self) -> Dict[str, Any]:
        """Тестирование подключения к Anthropic"""
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте API ключ.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Test"}]
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'response_length': len(response.content[0].text) if response.content else 0
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей Anthropic"""
        # Anthropic API не предоставляет список моделей, возвращаем известные
        return [
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229", 
            "claude-3-opus-20240229",
            "claude-2.1",
            "claude-2.0"
        ]


class DeepSeekProvider(OpenAICompatibleToolsMixin, AIProvider):
    """Провайдер DeepSeek через OpenAI-совместимый API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.model = model or settings.DEEPSEEK_MODEL
        self.base_url = base_url or settings.DEEPSEEK_BASE_URL
        self.client = None

        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                print("OpenAI библиотека не установлена")
            except Exception as e:
                print(f"Ошибка инициализации DeepSeek: {e}")

    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "DeepSeek провайдер не настроен"

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.settings.AI_RESPONSE_MAX_TOKENS,
                temperature=0.7,
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"Ошибка DeepSeek: {e}"

    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None

    def get_model_name(self) -> str:
        return f"DeepSeek {self.model}"

    def test_connection(self) -> Dict[str, Any]:
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте API ключ.'
            }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5,
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'base_url': self.base_url,
                'response_length': len(response.choices[0].message.content),
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }

    def get_available_models(self) -> List[str]:
        return [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
            "deepseek-reasoner",
        ]


class DeepSeekResponsesToolsMixin:
    """Адаптер инструментов через DeepSeek Responses API (spike #441).

    Переводит OpenAI-стиль истории рантайма коуча в input-элементы Responses
    (function_call / function_call_output) и нормализует output-элементы в тот
    же контракт {text, tool_calls}, что и остальные нативные провайдеры (#190).
    """

    def supports_native_tools(self) -> bool:
        return True

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        if not getattr(self, "client", None):
            return {"text": f"{type(self).__name__}: клиент не настроен", "tool_calls": []}

        request: Dict[str, Any] = {
            "model": self.model,
            "input": _messages_to_responses_input(messages),
            "instructions": system_prompt or None,
            "max_output_tokens": self.settings.AI_RESPONSE_MAX_TOKENS,
            # Tool selection/arguments must be deterministic (issue #440).
            "temperature": self.settings.AI_TOOLS_TEMPERATURE,
        }
        payload = [
            {
                "type": "function",
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["parameters"],
            }
            for schema in tools or []
        ]
        if payload:
            request["tools"] = payload

        try:
            response = self.client.responses.create(**request)
        except Exception as exc:
            return {"text": f"Ошибка {type(self).__name__}: {exc}", "tool_calls": []}

        result = responses_output_to_result(getattr(response, "output", None))
        # Spike #441: на финальном шаге output_text может быть None — но когда
        # в output нет message-элементов, честный fallback лучше пустой строки.
        if not result["text"]:
            fallback = getattr(response, "output_text", None)
            if isinstance(fallback, str) and fallback:
                result["text"] = fallback
        return result


def _client_supports_responses(client: Any) -> bool:
    """True, когда SDK-клиент имеет ресурс responses (openai>=1.59.0)."""
    return client is not None and hasattr(client, "responses")


def _item_value(item: Any, key: str, default: Any = None) -> Any:
    """Читает поле из dict-элемента или SDK-объекта (duck typing)."""
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _message_text_from_content_parts(content: Any) -> str:
    """Склеивает text-части content (список {text: str} или объекты .text)."""
    parts: List[str] = []
    for part in content or []:
        value = part.get("text") if isinstance(part, Mapping) else getattr(part, "text", None)
        if isinstance(value, str):
            parts.append(value)
    return "".join(parts)


def responses_output_to_result(output_items: Any) -> Dict[str, Any]:
    """Нормализует output-элементы Responses API в {text, tool_calls} (#441).

    Дискриминатор type: message → текст, function_call → {id, name, arguments},
    reasoning и прочие типы пропускаются (spike #441).
    """
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for item in output_items or []:
        item_type = str(_item_value(item, "type") or "").strip()
        if item_type == "message":
            text_parts.append(_message_text_from_content_parts(_item_value(item, "content")))
        elif item_type == "function_call":
            arguments = _item_value(item, "arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append(
                {
                    "id": str(_item_value(item, "call_id") or _item_value(item, "id") or ""),
                    "name": str(_item_value(item, "name") or ""),
                    "arguments": dict(arguments),
                }
            )
    return {"text": "".join(text_parts), "tool_calls": tool_calls}


def _messages_to_responses_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Проекция OpenAI-истории рантайма на input-элементы Responses (#441).

    assistant с tool_calls → assistant-item + function_call-items;
    tool-сообщение → function_call_output с tool_call_id;
    остальные роли — как есть (системный промпт передаётся instructions).
    """
    items: List[Dict[str, Any]] = []
    for message in messages or []:
        if not isinstance(message, Mapping):
            continue
        role = str(message.get("role") or "")
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": str(message.get("tool_call_id") or ""),
                    "output": str(message.get("content") or ""),
                }
            )
            continue
        tool_calls = message.get("tool_calls")
        if role == "assistant" and tool_calls:
            items.append({"role": "assistant", "content": str(message.get("content") or "")})
            for call in tool_calls:
                if not isinstance(call, Mapping):
                    continue
                arguments = call.get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {}
                items.append(
                    {
                        "type": "function_call",
                        "call_id": str(call.get("id") or call.get("call_id") or ""),
                        "name": str(call.get("name") or ""),
                        "arguments": dict(arguments),
                    }
                )
            continue
        items.append(
            {
                "role": role if role in {"user", "assistant", "system"} else "user",
                "content": str(message.get("content") or ""),
            }
        )
    return items


class DeepSeekResponsesProvider(DeepSeekResponsesToolsMixin, AIProvider):
    """Провайдер DeepSeek через Responses API (формат Codex, spike #441).

    Отдельный адаптер поверх того же клиента OpenAI SDK: формат ответа
    Responses API структурно отличается от chat.completions, поэтому этот
    класс НЕ переиспользует OpenAICompatibleToolsMixin и не подменяет base_url
    у обычного DeepSeekProvider (тот продолжает ходить в chat.completions).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.model = model or settings.DEEPSEEK_MODEL
        self.base_url = base_url or settings.DEEPSEEK_BASE_URL
        self.client = None

        if self.api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                # Codex P1 (#496): ранние 1.x-версии SDK не имеют ресурса responses —
                # провайдер обязан не врать про доступность в таком окружении.
                if _client_supports_responses(client):
                    self.client = client
                else:
                    print("Установленный openai SDK не поддерживает Responses API; обновите до openai>=1.59.0")
            except ImportError:
                print("OpenAI библиотека не установлена")
            except Exception as e:
                print(f"Ошибка инициализации DeepSeekResponsesProvider: {e}")

    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "DeepSeek Responses провайдер не настроен"

        try:
            input_items: List[Dict[str, Any]] = []
            if system_prompt:
                input_items.append({"role": "system", "content": system_prompt})
            input_items.append({"role": "user", "content": prompt})

            response = self.client.responses.create(
                model=self.model,
                input=input_items,
                max_output_tokens=self.settings.AI_RESPONSE_MAX_TOKENS,
            )
            result = responses_output_to_result(getattr(response, "output", None))
            text = result["text"] or str(getattr(response, "output_text", None) or "")
            return text

        except Exception as e:
            return f"Ошибка DeepSeekResponsesProvider: {e}"

    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None

    def get_model_name(self) -> str:
        return f"DeepSeek Responses {self.model}"

    def test_connection(self) -> Dict[str, Any]:
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте API ключ.'
            }

        try:
            response = self.client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": "Test"}],
                max_output_tokens=5,
            )
            # Codex P2 (#496): текст живёт в output-элементах, output_text может
            # быть None — меряем нормализованный текст, а не сырое поле.
            parsed = responses_output_to_result(getattr(response, "output", None))
            response_text = parsed["text"] or str(getattr(response, "output_text", None) or "")
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'base_url': self.base_url,
                'response_length': len(response_text),
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }

    def get_available_models(self) -> List[str]:
        return [
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "deepseek-chat",
            "deepseek-reasoner",
        ]


class GoogleGeminiProvider(AIProvider):
    """Провайдер Google Gemini через актуальный Google Gen AI SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings: Type[Settings] = Settings,
        emit_warnings: bool = True,
    ) -> None:
        self.settings = settings
        self.api_key = api_key or settings.GOOGLE_API_KEY
        self.emit_warnings = emit_warnings
        self.init_error: Optional[str] = None
        self.model_name = model or settings.GOOGLE_MODEL
        self.sdk_model_name = self._normalize_model_name(self.model_name)
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                self.init_error = "Google Gen AI SDK не установлен"
                self._emit_init_warning(self.init_error)
            except Exception as e:
                self.init_error = f"Ошибка инициализации Google Gemini: {e}"
                self._emit_init_warning(self.init_error)
                self.client = None

    def _emit_init_warning(self, message: str) -> None:
        if self.emit_warnings:
            print(message)

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        """Google Gen AI SDK принимает model id без legacy `models/` prefix."""
        return model_name.removeprefix("models/")

    @staticmethod
    def _response_text(response: object) -> str:
        try:
            text = getattr(response, "text", "")
        except Exception:
            return ""
        return text or ""
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return self.init_error or "Google Gemini провайдер не настроен"
        
        try:
            config = {
                "temperature": 0.7,
                "max_output_tokens": self.settings.AI_RESPONSE_MAX_TOKENS,
            }
            if system_prompt:
                config["system_instruction"] = system_prompt

            response = self.client.models.generate_content(
                model=self.sdk_model_name,
                contents=prompt,
                config=config,
            )
            return self._response_text(response)
            
        except Exception as e:
            return f"Ошибка Google Gemini: {e}"
    
    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None
    
    def get_model_name(self) -> str:
        return f"Google {self.model_name}"
    
    def test_connection(self) -> Dict[str, Any]:
        """Тестирование подключения к Google Gemini"""
        if not self.client:
            return {
                'success': False,
                'error': self.init_error or 'Клиент не инициализирован. Проверьте API ключ.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.models.generate_content(
                model=self.sdk_model_name,
                contents="Test",
                config={"max_output_tokens": 5},
            )
            response_text = self._response_text(response)
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model_name,
                'response_length': len(response_text)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей Google"""
        return [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]


class OllamaProvider(AIProvider):
    """Провайдер Ollama (локальные модели)"""
    
    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        settings: Type[Settings] = Settings,
    ) -> None:
        self.settings = settings
        self.model = model or settings.OLLAMA_MODEL
        self.host = host or settings.OLLAMA_HOST
        self.client = None
        
        try:
            import ollama
            self.client = ollama.Client(host=host)
            # Проверяем доступность
            self.client.list()
        except ImportError:
            print("Ollama библиотека не установлена")
        except Exception as e:
            print(f"Ошибка подключения к Ollama: {e}")
            self.client = None
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        if not self.client:
            return "Ollama не доступна. Убедитесь, что Ollama запущена локально."
        
        try:
            # Объединяем system и user промпты
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "user", "content": full_prompt}
                ]
            )
            
            return response['message']['content']
            
        except Exception as e:
            return f"Ошибка Ollama: {e}"
    
    def is_available(self) -> bool:
        if not self.client:
            return False
        
        try:
            # Проверяем, что модель доступна
            models = self.client.list()
            
            # Ollama возвращает ListResponse с атрибутом models
            if hasattr(models, 'models'):
                model_names = [getattr(m, 'model', '') for m in models.models]
            else:
                model_names = [m.get('name', '') for m in models.get('models', [])]
            
            # Точное совпадение или содержание имени модели
            return any(self.model == name or self.model in name for name in model_names)
        except Exception as e:
            print(f"Ollama is_available error: {e}")
            return False
    
    def get_model_name(self) -> str:
        return f"Ollama {self.model}"
    
    def test_connection(self) -> Dict[str, Any]:
        """Тестирование подключения к Ollama"""
        if not self.client:
            return {
                'success': False,
                'error': 'Клиент не инициализирован. Проверьте, что Ollama запущен.'
            }
        
        try:
            # Простой тестовый запрос
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": "Test"}]
            )
            return {
                'success': True,
                'message': 'Подключение успешно',
                'model': self.model,
                'host': self.host,
                'response_length': len(response['message']['content'])
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка подключения: {str(e)}'
            }
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей Ollama"""
        if not self.client:
            return []
        
        try:
            models = self.client.list()
            
            if hasattr(models, 'models'):
                model_names = [getattr(m, 'model', '') for m in models.models]
            else:
                model_names = [m.get('name', '') for m in models.get('models', [])]
            
            return sorted([name for name in model_names if name])
        except Exception as e:
            print(f"Ошибка получения моделей Ollama: {e}")
            return []


class AIProviderFactory:
    """Фабрика для создания AI провайдеров"""

    @staticmethod
    def _google_probe_provider() -> GoogleGeminiProvider:
        return GoogleGeminiProvider(emit_warnings=False)
    
    @staticmethod
    def create_provider(provider_type: str, **kwargs) -> Optional[AIProvider]:
        """
        Создать провайдер по типу
        
        Args:
            provider_type: 'openai', 'anthropic', 'deepseek', 'google', 'ollama'
            **kwargs: параметры для конкретного провайдера
        """
        # Динамический импорт Mock провайдера
        try:
            from models.mock_ai_provider import MockAIProvider
        except ImportError:
            MockAIProvider = None
        
        providers = {
            'openai': OpenAIProvider,
            'anthropic': AnthropicProvider,
            'deepseek': DeepSeekProvider,
            'deepseek_responses': DeepSeekResponsesProvider,
            'google': GoogleGeminiProvider,
            'ollama': OllamaProvider
        }
        
        if MockAIProvider:
            providers['mock'] = MockAIProvider
        
        provider_class = providers.get(provider_type.lower())
        if provider_class:
            # Для Ollama добавляем значения по умолчанию из Settings если не переданы
            if provider_type.lower() == 'ollama':
                if 'host' not in kwargs:
                    kwargs['host'] = Settings.OLLAMA_HOST
                if 'model' not in kwargs:
                    kwargs['model'] = Settings.OLLAMA_MODEL
            return provider_class(**kwargs)
        
        raise ValueError(f"Неизвестный провайдер: {provider_type}")
    
    @staticmethod
    def get_available_providers() -> Dict[str, bool]:
        """Получить список доступных провайдеров"""
        # Динамический импорт Mock провайдера
        try:
            from models.mock_ai_provider import MockAIProvider
            mock_available = True
        except ImportError:
            mock_available = False
        
        providers = {
            'OpenAI': OpenAIProvider(),
            'Anthropic': AnthropicProvider(),
            'DeepSeek': DeepSeekProvider(),
            'DeepSeek (Responses API)': DeepSeekResponsesProvider(),
            'Google Gemini': AIProviderFactory._google_probe_provider(),
            'Ollama': OllamaProvider(host=Settings.OLLAMA_HOST, model=Settings.OLLAMA_MODEL)
        }
        
        if mock_available:
            providers['Mock AI (Demo)'] = MockAIProvider()
        
        return {
            name: provider.is_available() 
            for name, provider in providers.items()
        }
    
    @staticmethod
    def get_first_available() -> Optional[AIProvider]:
        """Получить первый доступный провайдер"""
        # Приоритет: OpenAI -> Anthropic -> DeepSeek -> Google -> Ollama -> Mock
        # Создаём провайдеры лениво: конструкторы могут загружать тяжёлые SDK или
        # проверять локальные сервисы, поэтому после первого успеха остальные не
        # должны иметь побочных эффектов.
        provider_factories = [
            OpenAIProvider,
            AnthropicProvider,
            DeepSeekProvider,
            AIProviderFactory._google_probe_provider,
            lambda: OllamaProvider(
                host=Settings.OLLAMA_HOST,
                model=Settings.OLLAMA_MODEL,
            ),
        ]

        for create_provider in provider_factories:
            provider = create_provider()
            if provider.is_available():
                return provider

        try:
            from models.mock_ai_provider import MockAIProvider
        except ImportError:
            return None

        mock_provider = MockAIProvider()
        if mock_provider.is_available():
            return mock_provider
        
        return None
