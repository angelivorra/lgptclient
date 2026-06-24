"""
Modelo de lista para el log de eventos MIDI (QAbstractListModel para QML)
"""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot


class LogModel(QAbstractListModel):
    TextRole = Qt.UserRole + 1
    TimestampRole = Qt.UserRole + 2
    TagRole = Qt.UserRole + 3

    MAX_ENTRIES = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []

    def roleNames(self):
        return {
            self.TextRole: b"text",
            self.TimestampRole: b"timestamp",
            self.TagRole: b"tag",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._entries):
            return None
        entry = self._entries[index.row()]
        if role == self.TextRole:
            return entry["text"]
        if role == self.TimestampRole:
            return entry["timestamp"]
        if role == self.TagRole:
            return entry["tag"]
        return None

    @Slot(str, str, str)
    def addEntry(self, timestamp: str, text: str, tag: str):
        if len(self._entries) >= self.MAX_ENTRIES:
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._entries.pop(0)
            self.endRemoveRows()

        pos = len(self._entries)
        self.beginInsertRows(QModelIndex(), pos, pos)
        self._entries.append({"timestamp": timestamp, "text": text, "tag": tag})
        self.endInsertRows()

    @Slot()
    def clear(self):
        if not self._entries:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self._entries) - 1)
        self._entries.clear()
        self.endRemoveRows()

    @Slot(result=int)
    def entryCount(self) -> int:
        return len(self._entries)
