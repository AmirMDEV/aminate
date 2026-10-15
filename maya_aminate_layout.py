"""Small native layouts shared by Aminate's dockable forms."""

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


class ResponsiveRow(QtWidgets.QBoxLayout):
    """Keep a row compact; stack its controls when their minimum widths cannot fit."""

    def __init__(self, parent=None):
        super(ResponsiveRow, self).__init__(QtWidgets.QBoxLayout.LeftToRight, parent)

    def _visible_items(self):
        return [self.itemAt(i) for i in range(self.count()) if not self.itemAt(i).isEmpty()]

    def _stacked(self, width):
        items = self._visible_items()
        margins = self.contentsMargins()
        required = sum(item.minimumSize().width() for item in items)
        required += max(0, len(items) - 1) * max(0, self.spacing())
        return required > width - margins.left() - margins.right()

    def minimumSize(self):
        size = QtCore.QSize(0, 0)
        for item in self._visible_items():
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return QtCore.QSize(size.width() + margins.left() + margins.right(),
                            super(ResponsiveRow, self).minimumSize().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        margins = self.contentsMargins()
        inner_width = max(0, width - margins.left() - margins.right())
        items = self._visible_items()
        heights = [max(item.minimumSize().height(), item.heightForWidth(inner_width)
                       if item.hasHeightForWidth() else item.sizeHint().height()) for item in items]
        if self._stacked(width):
            height = sum(heights) + max(0, len(items) - 1) * max(0, self.spacing())
        else:
            height = max(heights, default=0)
        return height + margins.top() + margins.bottom()

    def setGeometry(self, rect):
        direction = QtWidgets.QBoxLayout.TopToBottom if self._stacked(rect.width()) else QtWidgets.QBoxLayout.LeftToRight
        if self.direction() != direction:
            self.setDirection(direction)
        super(ResponsiveRow, self).setGeometry(rect)
