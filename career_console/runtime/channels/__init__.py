"""Chat channels module with plugin architecture."""

from career_console.runtime.channels.base import BaseChannel
from career_console.runtime.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
