import sys
import os
import math
import time
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QColorDialog, QComboBox,
                             QLabel, QSlider, QFrame, QFileDialog, QMessageBox,
                             QLineEdit, QTextEdit, QDialog, QDialogButtonBox,
                             QSpinBox, QFontComboBox, QGroupBox, QGridLayout,
                             QProgressBar, QMenu, QAction, QSizePolicy)
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal, QTimer
from PyQt5.QtGui import (QPainter, QPen, QPainterPath, QPixmap, QColor,
                         QCursor, QMouseEvent, QKeyEvent)


class DrawingCanvas(QWidget):
    # 在类级别定义信号，而不是在__init__中
    coordinates_updated = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(1000, 700)
        self.setStyleSheet("background-color: white; border: 1px solid gray;")
        self.setFocusPolicy(Qt.StrongFocus)

        # 绘图属性
        self.current_tool = "矩形"
        self.current_color = QColor(Qt.black)
        self.pen_width = 2
        self.shapes = []
        self.current_path = None
        self.start_point = None
        self.drawing = False
        self.selected_shape_index = -1
        self.dragging = False
        self.drag_offset = QPoint()

        # 自由绘制相关
        self.freehand_points = []
        self.is_freehand_drawing = False

        # 双击检测相关
        self.last_click_time = 0
        self.double_click_interval = 250  # 双击时间间隔（毫秒）

    def keyPressEvent(self, event):
        """处理键盘事件"""
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            self.delete_selected_shape()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        try:
            current_time = time.time() * 1000  # 转换为毫秒

            # 检查是否为双击
            is_double_click = (current_time - self.last_click_time) < self.double_click_interval
            self.last_click_time = current_time

            if event.button() == Qt.LeftButton:
                pos = event.pos()

                # 双击选中图形
                if is_double_click:
                    for i, shape in enumerate(self.shapes):
                        if self.is_point_in_shape(pos, shape):
                            self.selected_shape_index = i
                            if self.selected_shape_index >= 0:
                                selected_shape = self.shapes[self.selected_shape_index]
                                selected_shape['color'] = QColor(self.current_color)
                                selected_shape['width'] = self.pen_width

                            # 发射坐标更新信号
                            center_x, center_y = self.get_selected_shape_center()
                            if center_x and center_y:
                                self.coordinates_updated.emit(center_x, center_y)

                            self.update()
                            return

                    # 如果没有双击到图形，取消选中状态
                    self.selected_shape_index = -1
                    self.dragging = False

                    # 发射坐标重置信号
                    self.coordinates_updated.emit(0, 0)

                    self.update()
                    return

                # 单击开始绘图或拖动
                if self.selected_shape_index >= 0 and self.is_point_in_shape(pos,
                                                                             self.shapes[self.selected_shape_index]):
                    # 如果点击了已选中的图形，开始拖动
                    shape = self.shapes[self.selected_shape_index]
                    self.dragging = True
                    center_x, center_y = self.get_shape_center(shape)
                    self.drag_offset = pos - QPoint(center_x, center_y)
                    self.update()
                    return

                # 如果没有选中图形或点击了空白区域，开始绘图
                self.drawing = True
                self.start_point = pos

                if self.current_tool in ["矩形", "正方形", "圆形", "椭圆", "三角形", "五角星", "直线", "梯形"]:
                    # 使用默认绘制方式，不预设参数
                    self.current_path = {
                        'shape': self.current_tool,
                        'start': self.start_point,
                        'end': self.start_point,
                        'color': QColor(self.current_color),
                        'width': self.pen_width,
                        'scale': 1.0,
                        'rotation': 0
                    }
                    self.update()
                elif self.current_tool == "自由绘制":
                    self.is_freehand_drawing = True
                    self.freehand_points = [pos]
                    self.update()

        except Exception as e:
            print(f"mousePressEvent error: {e}")

    def mouseMoveEvent(self, event):
        try:
            pos = event.pos()

            if self.dragging and event.buttons() & Qt.LeftButton and self.selected_shape_index >= 0:
                shape = self.shapes[self.selected_shape_index]
                center_x, center_y = self.get_shape_center(shape)
                new_center = pos - self.drag_offset

                dx = new_center.x() - center_x
                dy = new_center.y() - center_y

                # 修复：直接更新形状位置，不应用缩放
                if shape.get('type') == 'freehand':
                    # 移动自由绘制路径的所有点
                    new_points = []
                    for point in shape['points']:
                        new_points.append(QPoint(point.x() + dx, point.y() + dy))
                    shape['points'] = new_points
                else:
                    # 移动标准形状
                    shape['start'] = QPoint(shape['start'].x() + dx, shape['start'].y() + dy)
                    shape['end'] = QPoint(shape['end'].x() + dx, shape['end'].y() + dy)

                # 发射坐标更新信号
                new_center_x, new_center_y = self.get_shape_center(shape)
                self.coordinates_updated.emit(new_center_x, new_center_y)

                self.update()
                return

            if self.drawing and event.buttons() & Qt.LeftButton:
                if self.current_path and self.current_tool in ["矩形", "正方形", "圆形", "椭圆", "三角形", "五角星", "直线", "梯形"]:
                    # 更新end点
                    self.current_path['end'] = event.pos()
                    self.update()
                elif self.current_tool == "自由绘制" and self.is_freehand_drawing:
                    self.freehand_points.append(event.pos())
                    self.update()

        except Exception as e:
            print(f"mouseMoveEvent error: {e}")

    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.LeftButton:
                if self.dragging:
                    # 拖动结束
                    self.dragging = False

                if self.drawing:
                    self.drawing = False
                    if self.current_tool == "自由绘制" and self.is_freehand_drawing:
                        if len(self.freehand_points) > 1:
                            shape_data = {
                                'shape': '自由绘制',
                                'points': self.freehand_points.copy(),
                                'color': QColor(self.current_color),
                                'width': self.pen_width,
                                'type': 'freehand'
                            }
                            self.shapes.append(shape_data)
                            # 关键修改：画完后不选中图形
                            self.selected_shape_index = -1

                            # 更新坐标显示
                            center_x, center_y = self.get_freehand_center(shape_data)
                            self.coordinates_updated.emit(center_x, center_y)

                        self.is_freehand_drawing = False
                        self.freehand_points = []

                    elif self.current_path and self.current_tool in ["矩形", "正方形", "圆形", "椭圆", "三角形", "五角星", "直线", "梯形"]:
                        if (self.current_path['start'] != self.current_path['end']):
                            # 计算并保存形状参数
                            parameters = self.calculate_shape_parameters(self.current_path)

                            shape_data = {
                                'shape': self.current_path['shape'],
                                'start': QPoint(self.current_path['start']),
                                'end': QPoint(self.current_path['end']),
                                'color': QColor(self.current_path['color']),
                                'width': self.current_path['width'],
                                'scale': 1.0,
                                'rotation': 0,
                                'type': 'shape',
                                'parameters': parameters  # 保存计算出的参数
                            }

                            self.shapes.append(shape_data)
                            # 关键修改：画完后不选中图形
                            self.selected_shape_index = -1

                            # 更新坐标显示
                            center_x, center_y = self.get_shape_center(shape_data)
                            self.coordinates_updated.emit(center_x, center_y)

                        self.current_path = None

                    self.update()

        except Exception as e:
            print(f"mouseReleaseEvent error: {e}")
            self.drawing = False
            self.dragging = False
            self.current_path = None
            self.is_freehand_drawing = False
            self.freehand_points = []
            # 确保出错时也不选中任何图形
            self.selected_shape_index = -1

    def calculate_shape_parameters(self, shape):
        """计算并返回形状的参数"""
        start = shape['start']
        end = shape['end']
        shape_type = shape['shape']

        parameters = {}

        if shape_type == "矩形":
            width = abs(end.x() - start.x())
            height = abs(end.y() - start.y())
            parameters = {
                'width': max(1, width),  # 确保至少为1
                'height': max(1, height)
            }
        elif shape_type == "正方形":
            size = min(abs(end.x() - start.x()), abs(end.y() - start.y()))
            parameters = {'side': max(1, size)}
        elif shape_type == "圆形":
            diameter = min(abs(end.x() - start.x()), abs(end.y() - start.y()))
            parameters = {'radius': max(1, diameter // 2)}
        elif shape_type == "椭圆":
            major = abs(end.x() - start.x())
            minor = abs(end.y() - start.y())
            parameters = {
                'major': max(1, major),
                'minor': max(1, minor)
            }
        elif shape_type == "三角形":
            base = abs(end.x() - start.x())
            height_val = abs(end.y() - start.y())
            parameters = {
                'base': max(1, base),
                'height': max(1, height_val)
            }
        elif shape_type == "五角星":
            size = min(abs(end.x() - start.x()), abs(end.y() - start.y()))
            parameters = {'size': max(1, size)}
        elif shape_type == "直线":
            length = math.sqrt((end.x() - start.x()) ** 2 + (end.y() - start.y()) ** 2)
            parameters = {'length': max(1, int(length))}
        elif shape_type == "梯形":
            width_val = abs(end.x() - start.x())
            height_val = abs(end.y() - start.y())
            parameters = {
                'top_base': max(1, int(width_val * 0.6)),  # 估算值
                'bottom_base': max(1, width_val),
                'height': max(1, height_val)
            }

        print(f"计算形状参数: {shape_type} -> {parameters}")  # 调试信息
        return parameters

    def is_point_in_shape(self, point, shape):
        """检查点是否在形状内"""
        try:
            if shape.get('type') == 'freehand':
                return self.is_point_in_freehand(point, shape)
            else:
                if 'start' not in shape or 'end' not in shape:
                    return False

                start = shape['start']
                end = shape['end']

                x = min(start.x(), end.x())
                y = min(start.y(), end.y())
                width = abs(end.x() - start.x())
                height = abs(end.y() - start.y())

                scale = shape.get('scale', 1.0)
                width *= scale
                height *= scale

                return QRect(x - 15, y - 15, width + 30, height + 30).contains(point)
        except:
            return False

    def is_point_in_freehand(self, point, shape):
        """检查点是否在自由绘制路径附近"""
        points = shape.get('points', [])
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            # 简单的距离检查
            if self.point_to_line_distance(point, p1, p2) < 10:
                return True
        return False

    def point_to_line_distance(self, point, line_start, line_end):
        """计算点到线段的距离"""
        x, y = point.x(), point.y()
        x1, y1 = line_start.x(), line_start.y()
        x2, y2 = line_end.x(), line_end.y()

        A = x - x1
        B = y - y1
        C = x2 - x1
        D = y2 - y1

        dot = A * C + B * D
        len_sq = C * C + D * D

        if len_sq == 0:
            return math.sqrt(A * A + B * B)

        param = dot / len_sq

        if param < 0:
            xx, yy = x1, y1
        elif param > 1:
            xx, yy = x2, y2
        else:
            xx = x1 + param * C
            yy = y1 + param * D

        dx = x - xx
        dy = y - yy

        return math.sqrt(dx * dx + dy * dy)

    def get_selected_shape_center(self):
        """获取选中图形的中心点坐标"""
        if self.selected_shape_index >= 0 and self.selected_shape_index < len(self.shapes):
            shape = self.shapes[self.selected_shape_index]
            if shape.get('type') == 'freehand':
                return self.get_freehand_center(shape)
            else:
                return self.get_shape_center(shape)
        return None

    def get_freehand_center(self, shape):
        """获取自由绘制路径的中心点"""
        points = shape.get('points', [])
        if not points:
            return 0, 0

        x_sum = sum(p.x() for p in points)
        y_sum = sum(p.y() for p in points)
        return int(x_sum / len(points)), int(y_sum / len(points))

    def update_shape_position(self, x, y):
        """更新选中图形的位置 - 修复：直接移动，不创建新图形"""
        if self.selected_shape_index >= 0 and self.selected_shape_index < len(self.shapes):
            shape = self.shapes[self.selected_shape_index]
            current_center = self.get_selected_shape_center()
            if current_center:
                current_x, current_y = current_center
                dx = x - current_x
                dy = y - current_y

                if shape.get('type') == 'freehand':
                    # 移动自由绘制路径的所有点
                    new_points = []
                    for point in shape['points']:
                        new_points.append(QPoint(point.x() + dx, point.y() + dy))
                    shape['points'] = new_points
                else:
                    # 移动标准形状
                    shape['start'] = QPoint(shape['start'].x() + dx, shape['start'].y() + dy)
                    shape['end'] = QPoint(shape['end'].x() + dx, shape['end'].y() + dy)

                # 发射坐标更新信号
                self.coordinates_updated.connect(self.update_coordinates_display)

                self.update()

    def update_shape_rotation(self, rotation):
        """更新选中图形的旋转角度"""
        if self.selected_shape_index >= 0 and self.selected_shape_index < len(self.shapes):
            shape = self.shapes[self.selected_shape_index]
            shape['rotation'] = rotation % 360
            self.update()

    def update_shape_scale(self, scale):
        """更新选中图形的缩放比例"""
        if self.selected_shape_index >= 0 and self.selected_shape_index < len(self.shapes):
            shape = self.shapes[self.selected_shape_index]
            shape['scale'] = max(0.1, min(5.0, scale))

            # 更新坐标显示
            center_x, center_y = self.get_selected_shape_center()
            if center_x and center_y:
                self.coordinates_updated.emit(center_x, center_y)

            self.update()

    def update_selected_shape_color(self, color):
        """更新选中图形的颜色"""
        if self.selected_shape_index >= 0 and self.selected_shape_index < len(self.shapes):
            shape = self.shapes[self.selected_shape_index]
            shape['color'] = QColor(color)
            self.update()

    def update_selected_shape_width(self, width):
        """更新选中图形的线条粗细"""
        if self.selected_shape_index >= 0 and self.selected_shape_index < len(self.shapes):
            shape = self.shapes[self.selected_shape_index]
            shape['width'] = width
            self.update()

    def delete_selected_shape(self):
        """删除选中的图形"""
        if self.selected_shape_index >= 0 and self.selected_shape_index < len(self.shapes):
            self.shapes.pop(self.selected_shape_index)
            self.selected_shape_index = -1

            # 发射坐标重置信号
            self.coordinates_updated.emit(0, 0)

            self.update()
            return True
        return False

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            painter.fillRect(self.rect(), Qt.white)

            # 绘制所有已保存的图形
            for i, shape in enumerate(self.shapes):
                pen = QPen(shape['color'], shape['width'])
                painter.setPen(pen)

                if i == self.selected_shape_index:
                    painter.setPen(QPen(Qt.blue, 2, Qt.DashLine))
                    if shape.get('type') == 'freehand':
                        # 绘制自由绘制的选择框
                        points = shape.get('points', [])
                        if points:
                            x_coords = [p.x() for p in points]
                            y_coords = [p.y() for p in points]
                            x_min, x_max = min(x_coords), max(x_coords)
                            y_min, y_max = min(y_coords), max(y_coords)
                            painter.drawRect(x_min - 10, y_min - 10, x_max - x_min + 20, y_max - y_min + 20)
                    else:
                        # 绘制标准形状的选择框
                        start = shape['start']
                        end = shape['end']
                        x = min(start.x(), end.x())
                        y = min(start.y(), end.y())
                        width = abs(end.x() - start.x())
                        height = abs(end.y() - start.y())
                        scale = shape.get('scale', 1.0)
                        painter.drawRect(x - 10, y - 10, width * scale + 20, height * scale + 20)

                    # 绘制中心点
                    center_x, center_y = self.get_selected_shape_center()
                    if center_x and center_y:
                        painter.setPen(QPen(Qt.red, 6))
                        painter.drawPoint(center_x, center_y)

                    painter.setPen(pen)

                self.draw_shape(painter, shape)

            # 绘制当前正在绘制的图形（临时图形）
            if self.drawing:
                if self.current_tool == "自由绘制" and self.is_freehand_drawing and len(self.freehand_points) > 1:
                    pen = QPen(self.current_color, self.pen_width)
                    painter.setPen(pen)
                    path = QPainterPath()
                    path.moveTo(self.freehand_points[0])
                    for point in self.freehand_points[1:]:
                        path.lineTo(point)
                    painter.drawPath(path)

                elif self.current_path and self.current_tool in ["矩形", "正方形", "圆形", "椭圆", "三角形", "五角星", "直线", "梯形"]:
                    pen = QPen(self.current_color, self.pen_width)
                    painter.setPen(pen)
                    self.draw_shape(painter, self.current_path)

            painter.end()

        except Exception as e:
            print(f"paintEvent error: {e}")

    def get_shape_center(self, shape):
        """获取图形的中心点"""
        start = shape['start']
        end = shape['end']
        center_x = (start.x() + end.x()) // 2
        center_y = (start.y() + end.y()) // 2
        return center_x, center_y

    def draw_shape(self, painter, shape):
        try:
            shape_type = shape.get('shape', '矩形')

            if shape_type == "自由绘制":
                self.draw_freehand(painter, shape)
            else:
                start = shape['start']
                end = shape['end']

                if start == end:
                    return

                x = min(start.x(), end.x())
                y = min(start.y(), end.y())
                width = abs(end.x() - start.x())
                height = abs(end.y() - start.y())

                scale = shape.get('scale', 1.0)
                rotation = shape.get('rotation', 0)

                center_x, center_y = self.get_shape_center(shape)

                # 应用变换
                painter.save()
                painter.translate(center_x, center_y)
                painter.rotate(rotation)
                painter.scale(scale, scale)
                painter.translate(-center_x, -center_y)

                if shape_type == "矩形":
                    painter.drawRect(int(x), int(y), int(width), int(height))
                elif shape_type == "正方形":
                    size = min(width, height)
                    painter.drawRect(int(center_x - size / 2), int(center_y - size / 2), int(size), int(size))
                elif shape_type == "圆形":
                    diameter = min(width, height)
                    painter.drawEllipse(int(center_x - diameter / 2), int(center_y - diameter / 2), int(diameter),
                                        int(diameter))
                elif shape_type == "椭圆":
                    painter.drawEllipse(int(x), int(y), int(width), int(height))
                elif shape_type == "三角形":
                    path = QPainterPath()
                    path.moveTo(center_x, y)
                    path.lineTo(x, y + height)
                    path.lineTo(x + width, y + height)
                    path.lineTo(center_x, y)
                    painter.drawPath(path)
                elif shape_type == "五角星":
                    path = self.create_star_path(center_x, center_y, min(width, height) / 2)
                    painter.drawPath(path)
                elif shape_type == "直线":
                    painter.drawLine(start, end)
                elif shape_type == "梯形":
                    path = QPainterPath()
                    offset = width * 0.2
                    path.moveTo(x + offset, y)
                    path.lineTo(x + width - offset, y)
                    path.lineTo(x + width, y + height)
                    path.lineTo(x, y + height)
                    path.lineTo(x + offset, y)
                    painter.drawPath(path)

                painter.restore()

        except Exception as e:
            print(f"draw_shape error: {e}")

    def draw_freehand(self, painter, shape):
        """绘制自由绘制路径"""
        points = shape.get('points', [])
        if len(points) < 2:
            return

        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

    def create_star_path(self, center_x, center_y, radius):
        """创建五角星路径"""
        path = QPainterPath()

        for i in range(10):
            angle = math.pi / 2 - i * 2 * math.pi / 10
            r = radius if i % 2 == 0 else radius * 0.4
            x = center_x + r * math.cos(angle)
            y = center_y - r * math.sin(angle)

            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        path.closeSubpath()
        return path

    def clear_canvas(self):
        try:
            self.shapes.clear()
            self.selected_shape_index = -1
            self.dragging = False
            self.is_freehand_drawing = False
            self.freehand_points = []

            # 发射坐标重置信号
            self.coordinates_updated.emit(0, 0)

            self.update()
        except Exception as e:
            print(f"clear_canvas error: {e}")

    def save_drawing(self):
        try:
            file_path, selected_filter = QFileDialog.getSaveFileName(
                self, "保存绘图", "my_drawing.png", "PNG文件 (*.png);;JPEG文件 (*.jpg *.jpeg)"
            )

            if file_path:
                if selected_filter.startswith("JPEG"):
                    if not file_path.lower().endswith(('.jpg', '.jpeg')):
                        file_path += '.jpg'
                    format = 'JPEG'
                else:
                    if not file_path.lower().endswith('.png'):
                        file_path += '.png'
                    format = 'PNG'

                pixmap = QPixmap(self.size())
                pixmap.fill(Qt.white)

                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)

                for shape in self.shapes:
                    pen = QPen(shape['color'], shape['width'])
                    painter.setPen(pen)
                    self.draw_shape(painter, shape)

                painter.end()

                if pixmap.save(file_path, format):
                    QMessageBox.information(self, "成功", f"绘图已保存到: {file_path}")
                else:
                    QMessageBox.warning(self, "错误", "保存失败！")

        except Exception as e:
            print(f"save_drawing error: {e}")
            QMessageBox.critical(self, "错误", f"保存错误: {str(e)}")


class DrawingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.canvas = None
        self.color_map = {}
        self.init_ui()

        # 鼠标坐标显示定时器
        self.mouse_timer = QTimer()
        self.mouse_timer.timeout.connect(self.update_mouse_coordinates)
        self.mouse_timer.start(100)  # 每100ms更新一次

    def init_ui(self):
        self.setWindowTitle("奎氪绘图软件")
        # 增加窗口宽度以容纳更宽的第二列
        self.setGeometry(50, 50, 1650, 900)  # 宽度从1550增加到1650

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)

        self.canvas = DrawingCanvas()
        main_layout.addWidget(self.canvas)

        # 连接坐标更新信号
        self.canvas.coordinates_updated.connect(self.update_coordinates_display)

        # 设置右键菜单
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos):
        """显示右键菜单"""
        menu = QMenu(self)

        # 添加菜单项
        clear_action = QAction("清空画布", self)
        clear_action.triggered.connect(self.clear_canvas)
        menu.addAction(clear_action)

        save_action = QAction("保存绘图", self)
        save_action.triggered.connect(self.save_drawing)
        menu.addAction(save_action)

        export_action = QAction("输出按钮位置", self)
        export_action.triggered.connect(self.export_button_positions)
        menu.addAction(export_action)

        menu.addSeparator()

        exit_action = QAction("退出软件", self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)

        # 显示菜单
        menu.exec_(self.mapToGlobal(pos))

    def update_mouse_coordinates(self):
        """实时更新鼠标坐标显示"""
        try:
            # 获取鼠标在屏幕上的绝对坐标
            screen_pos = QCursor.pos()

            # 获取鼠标在应用程序窗口中的相对坐标
            window_pos = self.mapFromGlobal(screen_pos)

            # 获取鼠标在画布中的相对坐标
            canvas_pos = self.canvas.mapFromGlobal(screen_pos)

            # 更新坐标显示
            self.mouse_coord_label.setText(
                f"屏幕坐标: ({screen_pos.x()}, {screen_pos.y()}) | "
                f"窗口坐标: ({window_pos.x()}, {window_pos.y()}) | "
                f"画布坐标: ({canvas_pos.x()}, {canvas_pos.y()})"
            )
        except Exception as e:
            print(f"更新鼠标坐标错误: {e}")

    def create_toolbar(self):
        toolbar = QFrame()
        # 增加工具栏总宽度以适应更宽的第二列
        toolbar.setFixedWidth(650)  # 宽度从550增加到650
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                padding: 15px;
                border-right: 1px solid #dee2e6;
            }
            QLabel {
                font-weight: bold;
                color: #495057;
                margin-top: 8px;
                margin-bottom: 3px;
            }
            QPushButton {
                padding: 8px;
                border: none;
                border-radius: 4px;
                margin: 2px;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #ced4da;
                border-radius: 3px;
                font-size: 11px;
            }
        """)

        toolbar_main_layout = QHBoxLayout()
        toolbar.setLayout(toolbar_main_layout)

        left_column = QVBoxLayout()
        right_column = QVBoxLayout()  # 第二列，包含原来的第二列和第三列内容

        # 设置第二列的最小宽度
        right_column_widget = QWidget()
        right_column_widget.setLayout(right_column)
        right_column_widget.setMinimumWidth(250)  # 设置第二列的最小宽度
        right_column_widget.setMaximumWidth(300)  # 设置第二列的最大宽度

        # === 第一列：基础工具 ===
        # 完全按照原始代码的布局和间距
        brand_label = QLabel("奎氪绘图软件")
        brand_label.setStyleSheet("""
            QLabel {
                font-size: 14px; 
                font-weight: bold; 
                color: #2c3e50; 
                background-color: #3498db; 
                padding: 10px; 
                border-radius: 5px; 
                margin-bottom: 15px;
                border: 2px solid #2980b9;
            }
        """)
        left_column.addWidget(brand_label)

        left_column.addWidget(QLabel("图形选择:"))
        tools_layout = QGridLayout()
        tools_layout.setVerticalSpacing(4)  # 原始代码间距
        tools_layout.setHorizontalSpacing(4)  # 原始代码间距

        tools = ["矩形", "正方形", "圆形", "椭圆", "三角形", "五角星",
                 "直线", "自由绘制", "梯形"]
        self.tool_buttons = {}

        for i, tool in enumerate(tools):
            btn = QPushButton(tool)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tool: self.change_tool(t))
            if tool == "矩形":
                btn.setChecked(True)
            # 完全按照原始代码的按钮样式
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e9ecef;
                    color: #495057;
                    padding: 8px;
                    border: 1px solid #ced4da;
                    font-size: 10px;
                }
                QPushButton:checked {
                    background-color: #007bff;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #dee2e6;
                }
            """)
            tools_layout.addWidget(btn, i // 3, i % 3)
            self.tool_buttons[tool] = btn

        left_column.addLayout(tools_layout)

        left_column.addSpacing(12)  # 原始代码间距

        left_column.addWidget(QLabel("颜色选择:"))
        colors_layout = QGridLayout()
        colors_layout.setVerticalSpacing(4)  # 原始代码间距
        colors_layout.setHorizontalSpacing(4)  # 原始代码间距

        self.color_map = {
            "红色": QColor(255, 0, 0),
            "黄色": QColor(255, 255, 0),
            "蓝色": QColor(0, 0, 255),
            "绿色": QColor(0, 255, 0),
            "黑色": QColor(0, 0, 0),
            "白色": QColor(255, 255, 255),
            "粉色": QColor(255, 192, 203),
            "紫色": QColor(128, 0, 128)
        }

        self.color_buttons = {}

        for i, (color_name, color) in enumerate(self.color_map.items()):
            btn = QPushButton(color_name)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, c=color: self.change_color(c))
            if color_name == "黑色":
                btn.setChecked(True)

            text_color = "white" if color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114 < 128 else "black"

            # 完全按照原始代码的按钮样式
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color.name()};
                    color: {text_color};
                    padding: 8px;
                    border: 2px solid #495057;
                    font-size: 10px;
                }}
                QPushButton:checked {{
                    border: 4px solid #ff6b6b;
                }}
                QPushButton:hover {{
                    border: 3px solid #495057;
                }}
            """)
            colors_layout.addWidget(btn, i // 4, i % 4)
            self.color_buttons[color_name] = btn

        left_column.addLayout(colors_layout)

        left_column.addSpacing(12)  # 原始代码间距

        left_column.addWidget(QLabel("线条粗细:"))
        width_layout = QGridLayout()
        width_layout.setVerticalSpacing(4)  # 原始代码间距
        width_layout.setHorizontalSpacing(4)  # 原始代码间距

        self.width_sizes = [1, 2, 3, 5, 8, 10, 15, 20]
        self.width_buttons = {}

        for i, width in enumerate(self.width_sizes):
            btn = QPushButton(f"{width}px")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, w=width: self.change_width(w))
            if width == 2:
                btn.setChecked(True)
            # 完全按照原始代码的按钮样式
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e9ecef;
                    color: #495057;
                    padding: 8px;
                    border: 2px solid #ced4da;
                    font-size: 10px;
                }
                QPushButton:checked {
                    background-color: #6c757d;
                    color: white;
                    border: 2px solid #495057;
                }
                QPushButton:hover {
                    background-color: #dee2e6;
                }
            """)
            width_layout.addWidget(btn, i // 4, i % 4)
            self.width_buttons[width] = btn

        left_column.addLayout(width_layout)

        # 新增：线条粗细文本框
        width_input_layout = QHBoxLayout()
        width_input_layout.addWidget(QLabel("输入(1-20):"))
        self.width_input = QLineEdit()
        self.width_input.setFixedWidth(60)
        self.width_input.setText("2")
        self.width_input.setPlaceholderText("1-20px")
        self.width_input.editingFinished.connect(self.width_input_changed)
        width_input_layout.addWidget(self.width_input)
        width_input_layout.addWidget(QLabel("px"))
        width_input_layout.addStretch()
        left_column.addLayout(width_input_layout)

        left_column.addSpacing(12)  # 原始代码间距
        left_column.addWidget(QLabel("图形大小:"))
        scale_layout = QGridLayout()
        scale_layout.setVerticalSpacing(4)  # 原始代码间距
        scale_layout.setHorizontalSpacing(4)  # 原始代码间距

        self.scale_sizes = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0]
        self.scale_labels = ["10%", "20%", "30%", "50%", "80%", "100%", "110%", "120%", "130%", "150%", "180%", "200%"]
        self.scale_buttons = {}

        for i, (scale, label) in enumerate(zip(self.scale_sizes, self.scale_labels)):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=scale: self.change_scale(s))
            if scale == 1.0:
                btn.setChecked(True)
            # 完全按照原始代码的按钮样式
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e9ecef;
                    color: #495057;
                    padding: 6px;
                    border: 2px solid #ced4da;
                    font-size: 9px;
                }
                QPushButton:checked {
                    background-color: #28a745;
                    color: white;
                    border: 2px solid #1e7e34;
                }
                QPushButton:hover {
                    background-color: #dee2e6;
                }
            """)
            scale_layout.addWidget(btn, i // 4, i % 4)
            self.scale_buttons[scale] = btn

        left_column.addLayout(scale_layout)

        # 新增：图形大小文本框
        scale_input_layout = QHBoxLayout()
        scale_input_layout.addWidget(QLabel("输入(1-200):"))
        self.scale_input = QLineEdit()
        self.scale_input.setFixedWidth(60)
        self.scale_input.setText("100")
        self.scale_input.setPlaceholderText("1-200%")
        self.scale_input.editingFinished.connect(self.scale_input_changed)
        scale_input_layout.addWidget(self.scale_input)
        scale_input_layout.addWidget(QLabel("%"))
        scale_input_layout.addStretch()
        left_column.addLayout(scale_input_layout)

        left_column.addStretch()

        # === 第二列：整合原来的第二列和第三列内容 ===
        # 设置固定宽度和布局策略
        right_column.setContentsMargins(10, 0, 10, 0)  # 增加左右边距
        right_column.setSpacing(4)  # 原始代码间距

        # 中心点坐标显示（来自原来的第二列）
        self.center_label = QLabel("中心点: 无选中图形")
        self.center_label.setStyleSheet(
            "color: #495057; font-weight: bold; background-color: #e9ecef; padding: 6px; border-radius: 3px; font-size: 11px;")
        self.center_label.setWordWrap(True)  # 允许换行
        self.center_label.setMinimumHeight(40)  # 设置最小高度
        right_column.addWidget(self.center_label)

        right_column.addSpacing(12)  # 原始代码间距

        # 鼠标坐标显示（来自原来的第三列）
        self.mouse_coord_label = QLabel("鼠标坐标: 正在获取...")
        self.mouse_coord_label.setStyleSheet("""
            QLabel {
                color: #495057;
                background-color: #e9ecef;
                padding: 6px;
                border-radius: 3px;
                font-size: 10px;
                border: 1px solid #ced4da;
                margin-bottom: 8px;
            }
        """)
        self.mouse_coord_label.setWordWrap(True)
        self.mouse_coord_label.setMinimumHeight(60)  # 设置最小高度
        right_column.addWidget(self.mouse_coord_label)

        # 画布大小信息（来自原来的第三列）
        bg_info = QLabel(f"画布大小: 1000x700")
        bg_info.setStyleSheet(
            f"color: #6c757d; font-size: 11px; background-color: #e9ecef; padding: 4px; border-radius: 3px; border: 1px solid #ced4da; margin-bottom: 12px;")
        right_column.addWidget(bg_info)

        right_column.addSpacing(8)  # 原始代码间距
        right_column.addWidget(QLabel("功能操作:"))

        function_buttons_layout = QGridLayout()
        function_buttons_layout.setVerticalSpacing(6)  # 原始代码间距
        function_buttons_layout.setHorizontalSpacing(8)  # 原始代码间距

        # 第一行按钮 - 完全按照原始代码
        self.clear_btn = QPushButton("清空画布")
        self.clear_btn.clicked.connect(self.clear_canvas)
        self.clear_btn.setStyleSheet(
            "background-color: #dc3545; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        self.clear_btn.setFixedHeight(40)  # 固定高度
        function_buttons_layout.addWidget(self.clear_btn, 0, 0)

        self.save_btn = QPushButton("保存绘图")
        self.save_btn.clicked.connect(self.save_drawing)
        self.save_btn.setStyleSheet(
            "background-color: #17a2b8; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        self.save_btn.setFixedHeight(40)  # 固定高度
        function_buttons_layout.addWidget(self.save_btn, 0, 1)

        # 第二行按钮 - 完全按照原始代码
        self.export_button_positions_btn = QPushButton("输出按钮位置")
        self.export_button_positions_btn.clicked.connect(self.export_button_positions)
        self.export_button_positions_btn.setStyleSheet(
            "background-color: #9c27b0; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        self.export_button_positions_btn.setFixedHeight(40)  # 固定高度
        function_buttons_layout.addWidget(self.export_button_positions_btn, 1, 0, 1, 2)

        # 将功能按钮布局添加到容器中
        function_buttons_container = QWidget()
        function_buttons_container.setLayout(function_buttons_layout)
        right_column.addWidget(function_buttons_container)

        right_column.addStretch()

        # 添加两列到工具栏
        toolbar_main_layout.addLayout(left_column)
        toolbar_main_layout.addSpacing(15)  # 原始代码两列间距
        toolbar_main_layout.addWidget(right_column_widget)  # 使用固定宽度的widget

        return toolbar

    def width_input_changed(self):
        """处理线条粗细输入框变化"""
        try:
            text = self.width_input.text().strip()
            if text:
                width = int(text)
                if 1 <= width <= 20:
                    self.change_width(width)
                    self.width_input.setStyleSheet("border: 1px solid #ced4da;")
                else:
                    QMessageBox.warning(self, "警告", "请输入1-20之间的数字")
                    self.width_input.setStyleSheet("border: 1px solid #dc3545;")
            else:
                self.width_input.setStyleSheet("border: 1px solid #ced4da;")
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的数字")
            self.width_input.setStyleSheet("border: 1px solid #dc3545;")

    def scale_input_changed(self):
        """处理图形大小输入框变化"""
        try:
            text = self.scale_input.text().strip()
            if text:
                percent = int(text)
                if 1 <= percent <= 200:
                    scale = percent / 100.0  # 转换为比例
                    self.change_scale(scale)
                    self.scale_input.setStyleSheet("border: 1px solid #ced4da;")
                else:
                    QMessageBox.warning(self, "警告", "请输入1-200之间的数字")
                    self.scale_input.setStyleSheet("border: 1px solid #dc3545;")
            else:
                self.scale_input.setStyleSheet("border: 1px solid #ced4da;")
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的数字")
            self.scale_input.setStyleSheet("border: 1px solid #dc3545;")

    def export_button_positions(self):
        """输出按钮位置到JSON文件"""
        try:
            # 收集所有按钮的位置信息
            button_positions = []

            # 收集工具按钮
            for tool_name, button in self.tool_buttons.items():
                button_info = self.get_button_position_info(button, tool_name, "tool_button")
                button_positions.append(button_info)

            # 收集颜色按钮
            for color_name, button in self.color_buttons.items():
                button_info = self.get_button_position_info(button, color_name, "color_button")
                button_positions.append(button_info)

            # 收集线条粗细按钮
            for width, button in self.width_buttons.items():
                button_info = self.get_button_position_info(button, f"{width}px", "width_button")
                button_positions.append(button_info)

            # 收集图形大小按钮
            for scale, button in self.scale_buttons.items():
                button_info = self.get_button_position_info(button, f"{scale}倍", "scale_button")
                button_positions.append(button_info)

            # 收集功能按钮
            functional_buttons = {
                "clear_btn": ("清空画布", self.clear_btn),
                "save_btn": ("保存绘图", self.save_btn),
                "export_button_positions_btn": ("输出按钮位置", self.export_button_positions_btn)
            }

            for btn_id, (btn_name, button) in functional_buttons.items():
                button_info = self.get_button_position_info(button, btn_name, "functional_button")
                button_info["button_id"] = btn_id
                button_positions.append(button_info)

            # 收集输入框和其他UI元素的位置
            other_elements = [
                ("width_input", "线条粗细输入框", self.width_input, "input"),
                ("scale_input", "图形大小输入框", self.scale_input, "input"),
                ("mouse_coord_label", "鼠标坐标标签", self.mouse_coord_label, "label"),
                ("center_label", "中心点标签", self.center_label, "label"),
            ]

            for element_id, element_name, element, element_type in other_elements:
                if element:
                    element_info = self.get_ui_element_position_info(element, element_name, element_type)
                    element_info["element_id"] = element_id
                    button_positions.append(element_info)

            # 获取主窗口的位置
            window_info = {
                "name": "主窗口",
                "type": "window",
                "window_id": "main_window",
                "global_position": {
                    "top_left": {
                        "x": self.pos().x(),
                        "y": self.pos().y()
                    },
                    "top_right": {
                        "x": self.pos().x() + self.width(),
                        "y": self.pos().y()
                    },
                    "bottom_right": {
                        "x": self.pos().x() + self.width(),
                        "y": self.pos().y() + self.height()
                    },
                    "bottom_left": {
                        "x": self.pos().x(),
                        "y": self.pos().y() + self.height()
                    },
                    "center": {
                        "x": self.pos().x() + self.width() // 2,
                        "y": self.pos().y() + self.height() // 2
                    },
                    "size": {
                        "width": self.width(),
                        "height": self.height()
                    }
                },
                "screen_resolution": {
                    "width": QApplication.desktop().screenGeometry().width(),
                    "height": QApplication.desktop().screenGeometry().height()
                },
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            button_positions.append(window_info)

            # 创建输出目录
            output_dir = "button_positions"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # 生成文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"button_positions_{timestamp}.json"
            filepath = os.path.join(output_dir, filename)

            # 保存到JSON文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(button_positions, f, ensure_ascii=False, indent=2)

            # 显示成功消息
            QMessageBox.information(
                self,
                "成功",
                f"按钮位置信息已保存到:\n{filepath}\n\n共记录了 {len(button_positions)} 个UI元素的位置信息。"
            )

            # 在界面上显示信息
            print(f"按钮位置信息已保存到: {filepath}")
            print(f"共记录了 {len(button_positions)} 个UI元素")

        except Exception as e:
            error_msg = f"输出按钮位置失败: {str(e)}"
            print(error_msg)
            QMessageBox.critical(self, "错误", error_msg)

    def get_button_position_info(self, button, button_name, button_type):
        """获取按钮的位置信息"""
        try:
            # 获取按钮在屏幕上的全局位置
            global_pos = button.mapToGlobal(QPoint(0, 0))
            button_rect = button.geometry()

            # 获取按钮的四个顶点
            width = button_rect.width()
            height = button_rect.height()

            return {
                "name": button_name,
                "type": button_type,
                "button_id": f"{button_type}_{button_name}",
                "global_position": {
                    "top_left": {
                        "x": global_pos.x(),
                        "y": global_pos.y()
                    },
                    "top_right": {
                        "x": global_pos.x() + width,
                        "y": global_pos.y()
                    },
                    "bottom_right": {
                        "x": global_pos.x() + width,
                        "y": global_pos.y() + height
                    },
                    "bottom_left": {
                        "x": global_pos.x(),
                        "y": global_pos.y() + height
                    },
                    "center": {
                        "x": global_pos.x() + width // 2,
                        "y": global_pos.y() + height // 2
                    },
                    "size": {
                        "width": width,
                        "height": height
                    }
                },
                "is_enabled": button.isEnabled(),
                "is_visible": button.isVisible(),
                "text": button.text() if hasattr(button, 'text') else button_name,
                "timestamp": time.strftime("%Y-%m-d %H:%M:%S")
            }
        except Exception as e:
            print(f"获取按钮 {button_name} 位置失败: {e}")
            return {
                "name": button_name,
                "type": button_type,
                "button_id": f"{button_type}_{button_name}",
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

    def get_ui_element_position_info(self, element, element_name, element_type):
        """获取UI元素的位置信息"""
        try:
            # 获取元素在屏幕上的全局位置
            global_pos = element.mapToGlobal(QPoint(0, 0))
            element_rect = element.geometry()

            # 获取元素的四个顶点
            width = element_rect.width()
            height = element_rect.height()

            return {
                "name": element_name,
                "type": element_type,
                "element_id": f"{element_type}_{element_name}",
                "global_position": {
                    "top_left": {
                        "x": global_pos.x(),
                        "y": global_pos.y()
                    },
                    "top_right": {
                        "x": global_pos.x() + width,
                        "y": global_pos.y()
                    },
                    "bottom_right": {
                        "x": global_pos.x() + width,
                        "y": global_pos.y() + height
                    },
                    "bottom_left": {
                        "x": global_pos.x(),
                        "y": global_pos.y() + height
                    },
                    "center": {
                        "x": global_pos.x() + width // 2,
                        "y": global_pos.y() + height // 2
                    },
                    "size": {
                        "width": width,
                        "height": height
                    }
                },
                "is_enabled": element.isEnabled() if hasattr(element, 'isEnabled') else True,
                "is_visible": element.isVisible() if hasattr(element, 'isVisible') else True,
                "text": element.text() if hasattr(element, 'text') else element_name,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            print(f"获取UI元素 {element_name} 位置失败: {e}")
            return {
                "name": element_name,
                "type": element_type,
                "element_id": f"{element_type}_{element_name}",
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

    def change_tool(self, tool):
        """切换绘图工具"""
        if self.canvas:
            self.canvas.current_tool = tool

            for btn_tool, btn in self.tool_buttons.items():
                btn.setChecked(btn_tool == tool)

            if tool == "自由绘制":
                self.canvas.setCursor(Qt.CrossCursor)
            else:
                self.canvas.setCursor(Qt.CrossCursor)

    def change_color(self, color):
        """切换颜色"""
        if self.canvas:
            self.canvas.current_color = color

            for color_name, btn in self.color_buttons.items():
                btn_color = self.color_map[color_name]
                btn.setChecked(btn_color == color)

            self.canvas.update_selected_shape_color(color)

    def change_width(self, width):
        """改变线条粗细"""
        if self.canvas:
            self.canvas.pen_width = width

            for w, btn in self.width_buttons.items():
                btn.setChecked(w == width)

            # 更新输入框
            self.width_input.setText(str(width))
            self.width_input.setStyleSheet("border: 1px solid #ced4da;")

            self.canvas.update_selected_shape_width(width)

    def change_scale(self, scale):
        """改变图形大小"""
        if self.canvas:
            self.canvas.update_shape_scale(scale)

            for s, btn in self.scale_buttons.items():
                btn.setChecked(s == scale)

            # 更新输入框
            self.scale_input.setText(str(int(scale * 100)))
            self.scale_input.setStyleSheet("border: 1px solid #ced4da;")

    def update_coordinates_display(self, x, y):
        """实时更新坐标显示"""
        if self.canvas and self.canvas.selected_shape_index >= 0:
            self.center_label.setText(f"中心点: ({x}, {y})")
        else:
            self.center_label.setText("中心点: 无选中图形")

    def clear_canvas(self):
        """清空画布"""
        if self.canvas:
            self.canvas.clear_canvas()

    def save_drawing(self):
        """保存绘图"""
        if self.canvas:
            self.canvas.save_drawing()


def main():
    app = QApplication(sys.argv)

    window = DrawingApp()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()