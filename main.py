import sys
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QHBoxLayout, QAbstractItemView
)
from PyQt5.QtCore import Qt, QMimeData
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QMessageBox
import os

class RuleList(QListWidget):
    MIME_TYPE = 'application/x-rule-item'

    def __init__(self, xml_path, parent=None):
        super().__init__(parent)
        self.xml_path = xml_path
        self.parent_widget = parent
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.load_rules()

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        rule = item.data(Qt.UserRole)
        mime_data = QMimeData()
        rule_xml = ET.tostring(rule, encoding='utf-8', method='xml').decode('utf-8')
        mime_data.setData(self.MIME_TYPE, rule_xml.encode('utf-8'))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            rule_data = event.mimeData().data(self.MIME_TYPE).data()
            rule = ET.fromstring(rule_data.decode('utf-8'))
            insert_pos = self.indexAt(event.pos()).row()
            insert_pos = insert_pos if insert_pos != -1 else self.count()

            # 重新构建完整 rules 列表
            rules = self.rules_parent.findall('Rule')
            rules.insert(insert_pos, rule)

            # 清空原 rules_parent，再赋值
            self.rules_parent.clear()
            for r in rules:
                self.rules_parent.append(r)

            self.refresh_list()
            self.setCurrentRow(insert_pos)
            print(f"[拖拽] 插入规则到第 {insert_pos} 行：", rule.findtext('nameOverride'))
            event.acceptProposedAction()
        else:
            event.ignore()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if self.parent_widget:
            self.parent_widget.set_active_rule_list(self)

    def load_rules(self):
        self.tree = ET.parse(self.xml_path)
        self.root = self.tree.getroot()
        self.rules_parent = self.root.find('rules')
        # 倒序规则节点
        rules = list(reversed(self.rules_parent.findall('Rule')))
        self.rules_parent.clear()
        for rule in rules:
            self.rules_parent.append(rule)
        self.refresh_list()

    def refresh_list(self):
        self.clear()
        for idx, rule in enumerate(self.rules_parent.findall('Rule'), 1):
            override = rule.find('nameOverride')
            name = override.text.strip() if override is not None and override.text else '(无名称)'
            item = QListWidgetItem(f"{idx}. {name}")
            item.setData(Qt.UserRole, rule)
            self.addItem(item)

    def save_to_xml(self):
        self.rules_parent.clear()
        for i in reversed(range(self.count())):
            rule = self.item(i).data(Qt.UserRole)
            self.rules_parent.append(rule)
        self.tree.write(self.xml_path, encoding='utf-8', xml_declaration=True)
        print("已保存 XML 文件")

    def move_up(self):
        index = self.currentRow()
        self.setFocus()
        print(f"[move_up] 当前选中行：{index}")
        if index > 0:
            rule = self.item(index).data(Qt.UserRole)
            rule_above = self.item(index - 1).data(Qt.UserRole)
            rules = self.rules_parent.findall('Rule')
            rules.remove(rule)
            rules.remove(rule_above)
            rules.insert(index - 1, rule)
            rules.insert(index, rule_above)
            self.rules_parent.clear()
            for r in rules:
                self.rules_parent.append(r)
            self.refresh_list()
            self.setCurrentRow(index - 1)

    def move_down(self):
        index = self.currentRow()
        self.setFocus()
        print(f"[move_down] 当前选中行：{index}")
        if 0 <= index < self.count() - 1:
            rule = self.item(index).data(Qt.UserRole)
            rule_below = self.item(index + 1).data(Qt.UserRole)
            rules = self.rules_parent.findall('Rule')
            rules.remove(rule)
            rules.remove(rule_below)
            rules.insert(index, rule_below)
            rules.insert(index + 1, rule)
            self.rules_parent.clear()
            for r in rules:
                self.rules_parent.append(r)
            self.refresh_list()
            self.setCurrentRow(index + 1)

    def delete_selected(self):
        index = self.currentRow()
        item = self.currentItem()
        if item:
            rule = item.data(Qt.UserRole)
            self.rules_parent.remove(rule)
            self.refresh_list()
            if self.count() > 0:
                next_index = min(index, self.count() - 1)
                self.setCurrentRow(next_index)
            print("[删除] 删除规则：", rule.findtext("nameOverride"))

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("最后纪元过滤编辑器")
        self.resize(1200, 600)
        self.layout = QVBoxLayout(self)

        btn_layout = QHBoxLayout()
        self.load_btn = QPushButton('添加 XML 文件')
        self.load_btn.clicked.connect(self.load_xml)
        btn_layout.addWidget(self.load_btn)

        self.save_btn = QPushButton('保存所有 XML')
        self.save_btn.clicked.connect(self.save_all)
        btn_layout.addWidget(self.save_btn)

        self.layout.addLayout(btn_layout)
        self.rule_lists_layout = QHBoxLayout()
        self.layout.addLayout(self.rule_lists_layout)

        self.rule_lists = []
        self.active_rule_list = None

    def load_xml(self):
        default_path = os.path.join(
            os.getenv("USERPROFILE"),
            "AppData", "LocalLow", "Eleventh Hour Games", "Last Epoch", "Filters"
        )
        files, _ = QFileDialog.getOpenFileNames(self, '选择 XML 文件', default_path, 'XML 文件 (*.xml)')
        for file in files:
            vbox = QVBoxLayout()
            label = QLabel(file)
            rule_list = RuleList(file, parent=self)

            hbox = QHBoxLayout()
            for text, func in [
                ("⬆️ 上移", rule_list.move_up),
                ("⬇️ 下移", rule_list.move_down),
                ("🗑️ 删除", rule_list.delete_selected)
            ]:
                btn = QPushButton(text)
                btn.clicked.connect(func)
                hbox.addWidget(btn)

            vbox.addWidget(label)
            vbox.addWidget(rule_list)
            vbox.addLayout(hbox)
            self.rule_lists_layout.addLayout(vbox)
            self.rule_lists.append(rule_list)

    def save_all(self):
        for rule_list in self.rule_lists:
            rule_list.save_to_xml()
        QMessageBox.information(self, "保存成功", "所有 XML 文件已保存！")

    def set_active_rule_list(self, rule_list):
        self.active_rule_list = rule_list

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
