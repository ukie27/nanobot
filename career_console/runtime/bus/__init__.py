"""Message bus module for decoupled channel-agent communication."""

from career_console.runtime.bus.events import InboundMessage, OutboundMessage
from career_console.runtime.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
