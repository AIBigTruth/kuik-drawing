import sys
import os
import math
import random
import time
import re
import json
import requests
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QColorDialog, QComboBox,
                             QLabel, QSlider, QFrame, QFileDialog, QMessageBox,
                             QLineEdit, QTextEdit, QDialog, QDialogButtonBox,
                             QSpinBox, QFontComboBox, QGroupBox, QGridLayout,
                             QProgressBar)
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import (QPainter, QPen, QPainterPath, QPixmap, QColor, QFont,
                         QTextCursor, QCursor, QMouseEvent, QFontMetrics, QKeyEvent)

# 导入系统级鼠标控制
# 后版本增加按钮位置输出功能，json格式
try:
    import pyautogui

    MOUSE_CONTROL_AVAILABLE = True
except ImportError:
    MOUSE_CONTROL_AVAILABLE = False
    print("警告: 未安装pyautogui，无法进行物理鼠标控制")

# 尝试导入ollama
try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("警告: 未安装ollama，将使用requests方式调用")


class DrawingCanvas(QWidget):
    # 在类级别定义信号，而不是在__init__中
    coordinates_updated = pyqtSignal(int, int)
    shape_drawn = pyqtSignal(str, int, int, int, int)  # 形状绘制完成信号
    shape_moved = pyqtSignal(str, int, int)  # 新增：形状移动信号 (shape_type, center_x, center_y)

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

        # 需求描述
        self.requirement_description = ""

        # 形状参数（不再用于预设，仅用于记录）
        self.shape_parameters = {}

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
                    # 拖动结束，记录最终位置
                    self.dragging = False
                    if self.selected_shape_index >= 0:
                        shape = self.shapes[self.selected_shape_index]
                        center_x, center_y = self.get_shape_center(shape)
                        # 发射形状移动完成信号
                        self.shape_moved.emit(shape['shape'], center_x, center_y)

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

                            # 发射绘制完成信号 - 自由绘制
                            if len(self.freehand_points) >= 2:
                                x_coords = [p.x() for p in self.freehand_points]
                                y_coords = [p.y() for p in self.freehand_points]
                                start_x, start_y = min(x_coords), min(y_coords)
                                end_x, end_y = max(x_coords), max(y_coords)
                                self.shape_drawn.emit("自由绘制", start_x, start_y, end_x, end_y)

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

                            # 发射绘制完成信号 - 标准形状
                            start = self.current_path['start']
                            end = self.current_path['end']
                            start_x = min(start.x(), end.x())
                            start_y = min(start.y(), end.y())
                            end_x = max(start.x(), end.x())
                            end_y = max(start.y(), end.y())
                            self.shape_drawn.emit(self.current_path['shape'], start_x, start_y, end_x, end_y)

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

    def add_shape_directly(self, shape_type, start_point, end_point, parameters=None):
        """直接添加形状到画布，不通过鼠标事件"""
        # 如果没有提供参数，根据起点和终点计算
        if parameters is None:
            temp_shape = {
                'shape': shape_type,
                'start': start_point,
                'end': end_point
            }
            parameters = self.calculate_shape_parameters(temp_shape)

        shape_data = {
            'shape': shape_type,
            'start': QPoint(start_point),
            'end': QPoint(end_point),
            'color': QColor(self.current_color),
            'width': self.pen_width,
            'scale': 1.0,
            'rotation': 0,
            'type': 'shape',
            'parameters': parameters  # 保存参数
        }

        self.shapes.append(shape_data)
        # 关键修改：添加图形后不选中
        self.selected_shape_index = -1

        # 更新坐标显示
        center_x, center_y = self.get_shape_center(shape_data)
        self.coordinates_updated.emit(center_x, center_y)

        # 发射绘制完成信号
        start_x = min(start_point.x(), end_point.x())
        start_y = min(start_point.y(), end_point.y())
        end_x = max(start_point.x(), end_point.x())
        end_y = max(start_point.y(), end_point.y())
        self.shape_drawn.emit(shape_type, start_x, start_y, end_x, end_y)

        self.update()

    def move_shape_directly(self, shape_index, new_center_x, new_center_y):
        """直接移动指定索引的形状到新位置"""
        if 0 <= shape_index < len(self.shapes):
            shape = self.shapes[shape_index]
            current_center_x, current_center_y = self.get_shape_center(shape)

            dx = new_center_x - current_center_x
            dy = new_center_y - current_center_y

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
            self.coordinates_updated.emit(new_center_x, new_center_y)

            # 发射形状移动信号
            self.shape_moved.emit(shape['shape'], new_center_x, new_center_y)

            self.update()
            return True
        return False

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
                self.coordinates_updated.emit(x, y)

                # 发射形状移动信号
                self.shape_moved.emit(shape['shape'], x, y)

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
            self.shape_parameters = {}

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

    def set_requirement_description(self, description):
        """设置需求描述"""
        self.requirement_description = description


class ModelManager:
    """模型管理器"""

    def __init__(self):
        self.installed_models = []
        self.current_model = None

    def load_installed_models(self):
        """加载已安装的模型"""
        try:
            if OLLAMA_AVAILABLE:
                models_response = ollama.list()
                if 'models' in models_response:
                    self.installed_models = [model['model'] for model in models_response['models']]
                else:
                    self.installed_models = []

                print(f"已加载 {len(self.installed_models)} 个模型: {self.installed_models}")
                return self.installed_models
            else:
                print("Ollama 不可用，无法加载模型")
                return []
        except Exception as e:
            print(f"加载模型列表失败: {e}")
            return []

    def set_current_model(self, model_name):
        """设置当前使用的模型"""
        self.current_model = model_name
        print(f"已切换到模型: {model_name}")

    def get_current_model(self):
        """获取当前使用的模型"""
        return self.current_model

    def refresh_models(self):
        """刷新模型列表"""
        return self.load_installed_models()


class DrawingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.canvas = None
        self.color_map = {}
        self.model_manager = ModelManager()  # 新增：模型管理器
        self.init_ui()

        # 鼠标坐标显示定时器
        self.mouse_timer = QTimer()
        self.mouse_timer.timeout.connect(self.update_mouse_coordinates)
        self.mouse_timer.start(100)  # 每100ms更新一次

        # 操作记录相关变量
        self.is_recording = False
        self.operation_records = []
        self.record_start_time = None

        # 记录状态变量
        self.last_tool = None
        self.last_color = None
        self.last_width = None
        self.last_scale = None
        self.last_rotation = None

        # 新增：记录是否是第一次绘图
        self.is_first_drawing = True

        # 文本变化定时器
        self._text_change_timer = QTimer()
        self._text_change_timer.setSingleShot(True)
        self._text_change_timer.timeout.connect(self.update_step_numbers_in_training_text)

        # 大模型输出流程定时器
        self._output_flow_timer = QTimer()
        self._output_flow_timer.setSingleShot(True)
        self._output_flow_timer.timeout.connect(self.update_output_flow_text)

        # 当前执行步骤索引
        self.current_step_index = -1

        # 新增：记录图形索引映射
        self.shape_index_map = {}

        # 新增：训练数据计数定时器 - 修复：只用于更新计数，不更新下拉框
        self.training_data_timer = QTimer()
        self.training_data_timer.timeout.connect(self.update_training_data_count_only)
        self.training_data_timer.start(5000)  # 每5秒更新一次计数

        # 默认JSON文件路径
        self.current_json_file = "training_data.json"

        # 当前训练数据
        self.current_training_data = []
        self.current_data_index = -1

        # 新增：记录当前选中的数据索引，用于保持选择状态
        self._last_selected_index = -1

        # Ollama 配置
        self.OLLAMA_URL = "http://localhost:11434/api/generate"
        self.model_name = "deepseek-r1-15b-kuik100-100:latest"  # 默认模型

        # 流式输出相关
        self._streaming_output = ""  # 存储流式输出内容
        self._is_streaming = False  # 是否正在流式输出
        self._streaming_request = None  # 存储流式请求对象，用于停止
        self._should_stop_streaming = False  # 停止流式输出标志

    def init_ui(self):
        self.setWindowTitle("奎氪智能绘图软件")
        self.setGeometry(50, 50, 1800, 900)

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
        # 连接形状绘制完成信号
        self.canvas.shape_drawn.connect(self.record_shape_drawing)
        # 连接形状移动信号
        self.canvas.shape_moved.connect(self.record_shape_movement)

        # 加载模型列表
        self.load_models()

    def load_models(self):
        """加载可用的模型列表"""
        try:
            installed_models = self.model_manager.load_installed_models()

            # 更新模型选择下拉框
            self.model_combo.clear()
            if installed_models:
                for model in installed_models:
                    self.model_combo.addItem(model)

                # 设置默认选择
                if "deepseek-r1-15b-kuik100-100:latest" in installed_models:
                    index = installed_models.index("deepseek-r1-15b-kuik100-100:latest")
                    self.model_combo.setCurrentIndex(index)
                    self.model_manager.set_current_model("deepseek-r1-15b-kuik100-100:latest")
                else:
                    self.model_combo.setCurrentIndex(0)
                    self.model_manager.set_current_model(installed_models[0])

                self.model_status_label.setText(f"已加载 {len(installed_models)} 个模型")
                self.model_status_label.setStyleSheet("""
                    QLabel {
                        color: #28a745;
                        background-color: #d4edda;
                        padding: 5px;
                        border-radius: 3px;
                        font-size: 11px;
                        border: 1px solid #c3e6cb;
                    }
                """)
            else:
                self.model_combo.addItem("未检测到模型")
                self.model_status_label.setText("未检测到模型，请安装Ollama")
                self.model_status_label.setStyleSheet("""
                    QLabel {
                        color: #dc3545;
                        background-color: #f8d7da;
                        padding: 5px;
                        border-radius: 3px;
                        font-size: 11px;
                        border: 1px solid #f5c6cb;
                    }
                """)

        except Exception as e:
            print(f"加载模型失败: {e}")
            self.model_combo.clear()
            self.model_combo.addItem("加载模型失败")
            self.model_status_label.setText(f"加载模型失败: {str(e)}")
            self.model_status_label.setStyleSheet("""
                QLabel {
                    color: #dc3545;
                    background-color: #f8d7da;
                    padding: 5px;
                    border-radius: 3px;
                    font-size: 11px;
                    border: 1px solid #f5c6cb;
                }
            """)

    def refresh_models(self):
        """刷新模型列表"""
        try:
            installed_models = self.model_manager.refresh_models()

            # 保存当前选中的模型
            current_model = self.model_combo.currentText()

            # 更新模型选择下拉框
            self.model_combo.clear()
            if installed_models:
                for model in installed_models:
                    self.model_combo.addItem(model)

                # 尝试恢复之前的选择
                if current_model in installed_models:
                    index = installed_models.index(current_model)
                    self.model_combo.setCurrentIndex(index)
                    self.model_manager.set_current_model(current_model)
                else:
                    self.model_combo.setCurrentIndex(0)
                    self.model_manager.set_current_model(installed_models[0])

                self.model_status_label.setText(f"已刷新，共 {len(installed_models)} 个模型")
                self.model_status_label.setStyleSheet("""
                    QLabel {
                        color: #28a745;
                        background-color: #d4edda;
                        padding: 5px;
                        border-radius: 3px;
                        font-size: 11px;
                        border: 1px solid #c3e6cb;
                    }
                """)

                QMessageBox.information(self, "成功", f"已刷新模型列表，共 {len(installed_models)} 个模型")
            else:
                self.model_combo.addItem("未检测到模型")
                self.model_status_label.setText("未检测到模型，请安装Ollama")
                self.model_status_label.setStyleSheet("""
                    QLabel {
                        color: #dc3545;
                        background-color: #f8d7da;
                        padding: 5px;
                        border-radius: 3px;
                        font-size: 11px;
                        border: 1px solid #f5c6cb;
                    }
                """)
                QMessageBox.warning(self, "警告", "未检测到任何模型，请确保Ollama已安装并运行")

        except Exception as e:
            print(f"刷新模型失败: {e}")
            QMessageBox.critical(self, "错误", f"刷新模型列表失败: {str(e)}")

    def on_model_selection_changed(self, index):
        """当模型选择发生变化时"""
        if index >= 0:
            selected_model = self.model_combo.currentText()
            if selected_model != "未检测到模型" and selected_model != "加载模型失败":
                self.model_manager.set_current_model(selected_model)
                self.model_name = selected_model
                print(f"已切换到模型: {selected_model}")

                # 更新状态显示
                self.model_status_label.setText(f"当前模型: {selected_model}")
                self.model_status_label.setStyleSheet("""
                    QLabel {
                        color: #155724;
                        background-color: #d4edda;
                        padding: 5px;
                        border-radius: 3px;
                        font-size: 11px;
                        border: 1px solid #c3e6cb;
                    }
                """)

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

    def get_training_data_count(self):
        """获取训练数据文件中的实际数据条数"""
        try:
            file_path = self.current_json_file
            if not os.path.exists(file_path):
                return 0

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return len(data)
                else:
                    return 0
        except (json.JSONDecodeError, Exception) as e:
            print(f"读取训练数据文件错误: {e}")
            return 0

    def update_training_data_count_only(self):
        """只更新训练数据条数显示，不刷新下拉框"""
        count = self.get_training_data_count()
        self.training_data_label.setText(f"训练数据条数: {count} 条")

    def update_training_data_count(self):
        """更新训练数据条数显示并刷新下拉框"""
        count = self.get_training_data_count()
        self.training_data_label.setText(f"训练数据条数: {count} 条")
        # 更新数据选择下拉框
        self.update_data_selection_combo()

    def update_data_selection_combo(self):
        """更新数据选择下拉框"""
        try:
            if not os.path.exists(self.current_json_file):
                self.data_selection_combo.clear()
                self.data_selection_combo.addItem("无数据")
                self.current_data_index = -1
                self._last_selected_index = -1
                return

            with open(self.current_json_file, 'r', encoding='utf-8') as f:
                self.current_training_data = json.load(f)

            if not isinstance(self.current_training_data, list):
                self.current_training_data = []

            # 保存当前选中的索引
            current_selection = self.data_selection_combo.currentIndex()
            if current_selection >= 0:
                self._last_selected_index = current_selection

            self.data_selection_combo.blockSignals(True)
            self.data_selection_combo.clear()

            if self.current_training_data:
                for i, item in enumerate(self.current_training_data):
                    # 截取input内容作为显示文本，确保显示第几条
                    input_text = item.get('input', '')
                    # 确保显示"第X条"的格式，即使内容很长也要显示条数
                    display_text = f"第{i + 1}条: {input_text[:30]}{'...' if len(input_text) > 30 else ''}"
                    self.data_selection_combo.addItem(display_text)

                # 恢复之前的选择，如果之前的索引仍然有效
                if 0 <= self._last_selected_index < len(self.current_training_data):
                    self.data_selection_combo.setCurrentIndex(self._last_selected_index)
                    self.current_data_index = self._last_selected_index
                else:
                    # 如果之前的索引无效，不选择任何项
                    self.data_selection_combo.setCurrentIndex(-1)
                    self.current_data_index = -1
                    self._last_selected_index = -1
            else:
                self.data_selection_combo.addItem("无数据")
                self.current_data_index = -1
                self._last_selected_index = -1

            self.data_selection_combo.blockSignals(False)

        except Exception as e:
            print(f"更新数据选择下拉框错误: {e}")
            self.data_selection_combo.clear()
            self.data_selection_combo.addItem("加载失败")
            self.current_data_index = -1
            self._last_selected_index = -1

    def refresh_data_selection(self):
        """手动刷新数据选择下拉框"""
        self.update_data_selection_combo()

    def select_json_file(self):
        """选择要保存的JSON文件"""
        file_path, selected_filter = QFileDialog.getOpenFileName(
            self, "选择训练数据JSON文件", self.current_json_file, "JSON文件 (*.json)"
        )

        if file_path:
            self.current_json_file = file_path
            self.update_file_info_display()
            # 刷新数据条数显示
            self.update_training_data_count_only()
            # 更新数据选择下拉框
            self.refresh_data_selection()

    def load_json_data(self):
        """读取JSON文件并加载数据到界面"""
        try:
            if not os.path.exists(self.current_json_file):
                QMessageBox.warning(self, "错误", f"文件不存在: {self.current_json_file}")
                return

            with open(self.current_json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                QMessageBox.warning(self, "错误", "JSON文件格式不正确，应该是一个数组")
                return

            if not data:
                QMessageBox.information(self, "提示", "JSON文件中没有数据")
                return

            # 获取当前选中的数据索引
            current_index = self.data_selection_combo.currentIndex()
            if current_index < 0 or current_index >= len(data):
                QMessageBox.warning(self, "错误", "请先选择有效的数据条目")
                return

            # 加载选中的数据
            selected_data = data[current_index]

            # 解析input到需求描述
            input_text = selected_data.get('input', '')
            self.requirement_text.setPlainText(input_text)

            # 解析output到大模型训练文本
            output_text = selected_data.get('output', '')
            self.training_text.setPlainText(output_text)

            # 同步更新大模型输出流程
            self.update_output_flow_text()

            QMessageBox.information(self, "成功", f"已加载第{current_index + 1}条数据")

        except Exception as e:
            print(f"读取JSON文件错误: {e}")
            QMessageBox.critical(self, "错误", f"读取JSON文件失败: {str(e)}")

    def update_file_info_display(self):
        """更新文件信息显示"""
        file_name = os.path.basename(self.current_json_file)
        self.file_name_label.setText(f"文件名: {file_name}")

    def create_toolbar(self):
        toolbar = QFrame()
        toolbar.setFixedWidth(800)  # 增加宽度以容纳更长的下拉框
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
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QSpinBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QTextEdit {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QComboBox {
                padding: 6px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                min-width: 200px;
                max-height: 200px;
            }
            QComboBox QAbstractItemView {
                min-width: 300px;
                max-height: 200px;
            }
        """)

        toolbar_main_layout = QHBoxLayout()
        toolbar.setLayout(toolbar_main_layout)

        left_column = QVBoxLayout()
        middle_column = QVBoxLayout()
        right_column = QVBoxLayout()

        # === 第一列：基础工具 ===
        brand_label = QLabel("奎氪软件操作智能体（Agent）")
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

        tools = ["矩形", "正方形", "圆形", "椭圆", "三角形", "五角星",
                 "直线", "自由绘制", "梯形"]
        self.tool_buttons = {}

        for i, tool in enumerate(tools):
            btn = QPushButton(tool)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tool: self.change_tool(t))
            if tool == "矩形":
                btn.setChecked(True)
                self.last_tool = "矩形"
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

        left_column.addSpacing(12)

        left_column.addWidget(QLabel("颜色选择:"))
        colors_layout = QGridLayout()

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
                self.last_color = color

            text_color = "white" if color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114 < 128 else "black"

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

        left_column.addSpacing(12)

        left_column.addWidget(QLabel("线条粗细:"))
        width_layout = QGridLayout()

        self.width_sizes = [1, 2, 3, 5, 8, 10, 15, 20]
        self.width_buttons = {}

        for i, width in enumerate(self.width_sizes):
            btn = QPushButton(f"{width}px")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, w=width: self.change_width(w))
            if width == 2:
                btn.setChecked(True)
                self.last_width = width
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

        left_column.addSpacing(12)
        left_column.addWidget(QLabel("图形大小:"))
        scale_layout = QGridLayout()

        self.scale_sizes = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0]
        self.scale_labels = ["10%", "20%", "30%", "50%", "80%", "100%", "110%", "120%", "130%", "150%", "180%", "200%"]
        self.scale_buttons = {}

        for i, (scale, label) in enumerate(zip(self.scale_sizes, self.scale_labels)):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=scale: self.change_scale(s))
            if scale == 1.0:
                btn.setChecked(True)
                self.last_scale = scale
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

        # 新增：JSON文件选择和显示区域
        left_column.addSpacing(12)
        left_column.addWidget(QLabel("训练数据文件:"))

        # 选择JSON文件按钮
        self.select_json_btn = QPushButton("选择JSON文件")
        self.select_json_btn.clicked.connect(self.select_json_file)
        self.select_json_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 8px;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        left_column.addWidget(self.select_json_btn)

        # 文件名显示
        self.file_name_label = QLabel("文件名: training_data.json")
        self.file_name_label.setStyleSheet("""
            QLabel {
                color: #495057;
                background-color: #e9ecef;
                padding: 6px;
                border-radius: 3px;
                font-size: 10px;
                border: 1px solid #ced4da;
                margin-top: 6px;
            }
        """)
        self.file_name_label.setWordWrap(True)
        left_column.addWidget(self.file_name_label)

        # 训练数据条数显示
        initial_count = self.get_training_data_count()
        self.training_data_label = QLabel(f"训练数据条数: {initial_count} 条")
        self.training_data_label.setStyleSheet("""
            QLabel {
                color: #155724;
                background-color: #d4edda;
                padding: 6px;
                border-radius: 3px;
                font-size: 11px;
                border: 1px solid #c3e6cb;
                margin-top: 8px;
                font-weight: bold;
            }
        """)
        left_column.addWidget(self.training_data_label)

        left_column.addStretch()

        # === 第二列：智能控制和设置 ===
        middle_column.setContentsMargins(0, 0, 10, 0)
        middle_column.setSpacing(4)  # 减小列内间距

        # 模型选择模块
        middle_column.addWidget(QLabel("模型选择:"))

        model_selection_layout = QVBoxLayout()
        model_selection_layout.setSpacing(4)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.currentIndexChanged.connect(self.on_model_selection_changed)
        model_selection_layout.addWidget(self.model_combo)

        # 刷新模型按钮
        refresh_btn_layout = QHBoxLayout()
        self.refresh_models_btn = QPushButton("刷新模型列表")
        self.refresh_models_btn.clicked.connect(self.refresh_models)
        self.refresh_models_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                padding: 6px;
                border: none;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                margin-top: 2px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        refresh_btn_layout.addWidget(self.refresh_models_btn)
        refresh_btn_layout.addStretch()
        model_selection_layout.addLayout(refresh_btn_layout)

        # 模型状态显示
        self.model_status_label = QLabel("正在加载模型...")
        self.model_status_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                background-color: #f8f9fa;
                padding: 4px;
                border-radius: 3px;
                font-size: 10px;
                border: 1px solid #dee2e6;
                margin-top: 2px;
            }
        """)
        model_selection_layout.addWidget(self.model_status_label)
        middle_column.addLayout(model_selection_layout)

        middle_column.addSpacing(8)

        # 需求描述部分
        middle_column.addWidget(QLabel("需求描述:"))
        self.requirement_text = QTextEdit()
        self.requirement_text.setPlaceholderText("请输入您的绘图需求，例如：画一个红色的椭圆在画布中央")
        self.requirement_text.setMaximumHeight(70)  # 缩小高度
        middle_column.addWidget(self.requirement_text)

        # 修改：创建按钮水平布局，包含"智能体画图"和"停止生成"按钮
        button_layout = QHBoxLayout()

        self.confirm_btn = QPushButton("智能体画图")
        self.confirm_btn.clicked.connect(self.confirm_requirement_description)
        self.confirm_btn.setStyleSheet(
            "background-color: #28a745; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        button_layout.addWidget(self.confirm_btn)

        # 新增：停止生成按钮
        self.stop_generate_btn = QPushButton("停止生成")
        self.stop_generate_btn.clicked.connect(self.stop_generation)
        self.stop_generate_btn.setStyleSheet(
            "background-color: #dc3545; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        self.stop_generate_btn.setEnabled(False)  # 初始不可用
        button_layout.addWidget(self.stop_generate_btn)

        middle_column.addLayout(button_layout)

        middle_column.addSpacing(8)

        self.center_label = QLabel("中心点: 无选中图形")
        self.center_label.setStyleSheet(
            "color: #495057; font-weight: bold; background-color: #e9ecef; padding: 6px; border-radius: 3px; font-size: 11px;")
        middle_column.addWidget(self.center_label)

        middle_column.addSpacing(8)

        # 调整：先显示大模型流式输出
        middle_column.addWidget(QLabel("大模型流式输出:"))
        self.streaming_output_text = QTextEdit()
        self.streaming_output_text.setPlaceholderText("这里将显示大模型的实时流式输出...")
        self.streaming_output_text.setMinimumHeight(120)
        self.streaming_output_text.setReadOnly(True)
        self.streaming_output_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #ced4da;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        middle_column.addWidget(self.streaming_output_text)

        # 流式输出进度条
        self.streaming_progress = QProgressBar()
        self.streaming_progress.setVisible(False)
        self.streaming_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ced4da;
                border-radius: 3px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 2px;
            }
        """)
        middle_column.addWidget(self.streaming_progress)

        middle_column.addSpacing(8)

        # 调整：后显示大模型输出描述
        middle_column.addWidget(QLabel("大模型输出描述:"))
        self.model_output_text = QTextEdit()
        self.model_output_text.setPlaceholderText("这里将显示大模型对需求的分析和操作步骤...")
        self.model_output_text.setMinimumHeight(120)  # 适当缩小高度
        self.model_output_text.setReadOnly(True)
        middle_column.addWidget(self.model_output_text)

        middle_column.addSpacing(8)

        # 数据选择部分
        middle_column.addWidget(QLabel("数据选择:"))

        # 数据选择下拉框
        data_selection_layout = QVBoxLayout()
        data_selection_layout.setSpacing(4)
        data_selection_layout.addWidget(QLabel("选择数据条目:"))
        self.data_selection_combo = QComboBox()
        self.data_selection_combo.setMinimumWidth(220)
        self.data_selection_combo.currentIndexChanged.connect(self.on_data_selection_changed)
        data_selection_layout.addWidget(self.data_selection_combo)

        # 刷新数据选择下拉框按钮
        refresh_data_layout = QHBoxLayout()
        self.refresh_data_btn = QPushButton("刷新数据列表")
        self.refresh_data_btn.clicked.connect(self.refresh_data_selection)
        self.refresh_data_btn.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                padding: 6px;
                border: none;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                margin-top: 2px;
            }
            QPushButton:hover {
                background-color: #5a32a3;
            }
        """)
        refresh_data_layout.addWidget(self.refresh_data_btn)
        refresh_data_layout.addStretch()
        data_selection_layout.addLayout(refresh_data_layout)

        # 添加当前选择状态显示
        self.selection_status_label = QLabel("当前未选择数据")
        self.selection_status_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                background-color: #f8f9fa;
                padding: 4px;
                border-radius: 3px;
                font-size: 10px;
                border: 1px solid #dee2e6;
                margin-top: 2px;
            }
        """)
        data_selection_layout.addWidget(self.selection_status_label)

        middle_column.addLayout(data_selection_layout)

        middle_column.addStretch()

        # === 第三列：大模型训练和输出流程 ===
        right_column.setSpacing(6)  # 减小列内间距

        # 在第三列上方添加鼠标坐标和画布大小信息
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
        right_column.addWidget(self.mouse_coord_label)

        mouse_status = "可用" if MOUSE_CONTROL_AVAILABLE else "不可用"
        status_color = "#28a745" if MOUSE_CONTROL_AVAILABLE else "#dc3545"
        bg_info = QLabel(f"画布大小: 1000x700 | 鼠标控制: {mouse_status}")
        bg_info.setStyleSheet(
            f"color: #6c757d; font-size: 11px; background-color: #e9ecef; padding: 4px; border-radius: 3px; border: 1px solid {status_color}; margin-bottom: 12px;")
        right_column.addWidget(bg_info)

        right_column.addWidget(QLabel("大模型训练文本:"))
        self.training_text = QTextEdit()
        self.training_text.setPlaceholderText("这里将显示简化的操作流程文本，用于大模型训练...\n\n您可以手动编辑此文本，然后点击\"根据大模型画图\"按钮自动执行。")
        self.training_text.setMinimumHeight(160)  # 调整高度
        self.training_text.textChanged.connect(self.on_training_text_changed)
        right_column.addWidget(self.training_text)

        right_column.addSpacing(8)

        right_column.addWidget(QLabel("大模型输出流程:"))
        self.output_flow_text = QTextEdit()
        self.output_flow_text.setPlaceholderText("这里将显示格式化后的操作流程，每行一个步骤...")
        self.output_flow_text.setMinimumHeight(160)  # 调整高度
        self.output_flow_text.setReadOnly(True)
        right_column.addWidget(self.output_flow_text)

        right_column.addSpacing(8)

        # 记录状态标签
        self.record_status_label = QLabel("记录状态: 未开始")
        self.record_status_label.setStyleSheet(
            "color: #6c757d; font-weight: bold; background-color: #e9ecef; padding: 6px; border-radius: 3px; font-size: 11px;")
        right_column.addWidget(self.record_status_label)

        right_column.addSpacing(8)
        right_column.addWidget(QLabel("功能操作:"))

        function_buttons_layout = QGridLayout()
        function_buttons_layout.setVerticalSpacing(6)  # 减小按钮间垂直间距
        function_buttons_layout.setHorizontalSpacing(8)  # 减小按钮间水平间距

        # 第一行按钮
        self.clear_btn = QPushButton("清空画布")
        self.clear_btn.clicked.connect(self.clear_canvas)
        self.clear_btn.setStyleSheet(
            "background-color: #dc3545; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        function_buttons_layout.addWidget(self.clear_btn, 0, 0)

        self.save_btn = QPushButton("保存绘图")
        self.save_btn.clicked.connect(self.save_drawing)
        self.save_btn.setStyleSheet(
            "background-color: #17a2b8; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        function_buttons_layout.addWidget(self.save_btn, 0, 1)

        # 第二行按钮
        self.start_record_btn = QPushButton("开始记录操作")
        self.start_record_btn.clicked.connect(self.start_recording)
        self.start_record_btn.setStyleSheet(
            "background-color: #ffc107; color: black; padding: 10px; font-size: 11px; font-weight: bold;")
        function_buttons_layout.addWidget(self.start_record_btn, 1, 0)

        self.append_record_btn = QPushButton("追加记录操作")  # 新增：追加记录按钮
        self.append_record_btn.clicked.connect(self.append_recording)
        self.append_record_btn.setStyleSheet(
            "background-color: #20c997; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        function_buttons_layout.addWidget(self.append_record_btn, 1, 1)

        # 第三行按钮
        self.save_record_btn = QPushButton("保存操作记录")
        self.save_record_btn.clicked.connect(self.save_recording)
        self.save_record_btn.setStyleSheet(
            "background-color: #6f42c1; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        self.save_record_btn.setEnabled(False)
        function_buttons_layout.addWidget(self.save_record_btn, 2, 0)

        self.execute_llm_btn = QPushButton("大模型画图")
        self.execute_llm_btn.clicked.connect(self.execute_llm_instructions)
        self.execute_llm_btn.setStyleSheet(
            "background-color: #20c997; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        function_buttons_layout.addWidget(self.execute_llm_btn, 2, 1)

        # 第四行按钮
        self.save_training_btn = QPushButton("保存训练集")
        self.save_training_btn.clicked.connect(self.save_training_data)
        self.save_training_btn.setStyleSheet(
            "background-color: #fd7e14; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        function_buttons_layout.addWidget(self.save_training_btn, 3, 0)

        # 新增：输出按钮位置按钮
        self.export_button_positions_btn = QPushButton("输出按钮位置")
        self.export_button_positions_btn.clicked.connect(self.export_button_positions)
        self.export_button_positions_btn.setStyleSheet(
            "background-color: #9c27b0; color: white; padding: 10px; font-size: 11px; font-weight: bold;")
        function_buttons_layout.addWidget(self.export_button_positions_btn, 3, 1)

        # 第五行按钮
        # 修改：将读取JSON文件按钮移到功能操作区
        self.load_json_btn = QPushButton("读取JSON文件")
        self.load_json_btn.clicked.connect(self.load_json_data)
        self.load_json_btn.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a32a3;
            }
        """)
        function_buttons_layout.addWidget(self.load_json_btn, 4, 0, 1, 2)

        right_column.addLayout(function_buttons_layout)

        right_column.addStretch()

        toolbar_main_layout.addLayout(left_column)
        toolbar_main_layout.addSpacing(15)
        toolbar_main_layout.addLayout(middle_column)
        toolbar_main_layout.addSpacing(15)
        toolbar_main_layout.addLayout(right_column)

        return toolbar

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
                "start_record_btn": ("开始记录操作", self.start_record_btn),
                "append_record_btn": ("追加记录操作", self.append_record_btn),
                "save_record_btn": ("保存操作记录", self.save_record_btn),
                "execute_llm_btn": ("大模型画图", self.execute_llm_btn),
                "save_training_btn": ("保存训练集", self.save_training_btn),
                "load_json_btn": ("读取JSON文件", self.load_json_btn),
                "confirm_btn": ("智能体画图", self.confirm_btn),
                "stop_generate_btn": ("停止生成", self.stop_generate_btn),
                "refresh_models_btn": ("刷新模型列表", self.refresh_models_btn),
                "refresh_data_btn": ("刷新数据列表", self.refresh_data_btn),
                "select_json_btn": ("选择JSON文件", self.select_json_btn),
                "export_button_positions_btn": ("输出按钮位置", self.export_button_positions_btn)
            }

            for btn_id, (btn_name, button) in functional_buttons.items():
                button_info = self.get_button_position_info(button, btn_name, "functional_button")
                button_info["button_id"] = btn_id
                button_positions.append(button_info)

            # 收集其他UI元素的位置
            other_elements = [
                ("model_combo", "模型选择下拉框", self.model_combo, "combo_box"),
                ("data_selection_combo", "数据选择下拉框", self.data_selection_combo, "combo_box"),
                ("requirement_text", "需求描述文本框", self.requirement_text, "text_edit"),
                ("training_text", "大模型训练文本框", self.training_text, "text_edit"),
                ("output_flow_text", "大模型输出流程文本框", self.output_flow_text, "text_edit"),
                ("streaming_output_text", "大模型流式输出文本框", self.streaming_output_text, "text_edit"),
                ("model_output_text", "大模型输出描述文本框", self.model_output_text, "text_edit"),
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
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
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

    def on_data_selection_changed(self, index):
        """当数据选择发生变化时"""
        self.current_data_index = index
        self._last_selected_index = index

        # 更新选择状态显示
        if index >= 0:
            self.selection_status_label.setText(f"当前选择: 第{index + 1}条数据")
            self.selection_status_label.setStyleSheet("""
                QLabel {
                    color: #155724;
                    background-color: #d4edda;
                    padding: 4px;
                    border-radius: 3px;
                    font-size: 10px;
                    border: 1px solid #c3e6cb;
                    margin-top: 2px;
                }
            """)
        else:
            self.selection_status_label.setText("当前未选择数据")
            self.selection_status_label.setStyleSheet("""
                QLabel {
                    color: #6c757d;
                    background-color: #f8f9fa;
                    padding: 4px;
                    border-radius: 3px;
                    font-size: 10px;
                    border: 1px solid #dee2e6;
                    margin-top: 2px;
                }
            """)

    def save_training_data(self):
        """保存训练数据到JSON文件"""
        try:
            # 获取需求描述和训练文本
            input_text = self.requirement_text.toPlainText().strip()
            output_text = self.training_text.toPlainText().strip()

            if not input_text:
                QMessageBox.warning(self, "提示", "需求描述不能为空！")
                return

            if not output_text:
                QMessageBox.warning(self, "提示", "大模型训练文本不能为空！")
                return

            # 构建数据
            training_data = {
                "instruction": "现在你是智能绘图软件，图形选择有圆形、正方形、椭圆、矩形、三角形、五角星、直线、梯形，颜色有红色、黄色、蓝色、绿色、黑色、白色、粉色、紫色。要求根据描述输出画图的操作步骤。输出格式要严格遵守，输出格式例子：第1步，选择绘图工具为矩形；第2步，选择颜色为黑色；第3步，画一个矩形，调整图形位置到(406, 432)，设置宽度为160px，高度为143px；第4步，选择绘图工具为三角形；等等",
                "input": input_text,
                "output": output_text
            }

            # 文件路径
            file_path = self.current_json_file

            # 读取现有数据或创建新列表
            existing_data = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = []
                except (json.JSONDecodeError, Exception) as e:
                    print(f"读取现有文件出错，创建新文件: {e}")
                    existing_data = []

            # 追加新数据
            existing_data.append(training_data)

            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

            # 更新显示条数
            self.update_training_data_count_only()

            QMessageBox.information(self, "成功", f"训练数据已保存到: {file_path}\n当前共有 {len(existing_data)} 条训练数据")

        except Exception as e:
            print(f"保存训练数据错误: {e}")
            QMessageBox.critical(self, "错误", f"保存训练数据失败: {str(e)}")

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

            self.canvas.update_selected_shape_width(width)

    def change_scale(self, scale):
        """改变图形大小"""
        if self.canvas:
            self.canvas.update_shape_scale(scale)

            for s, btn in self.scale_buttons.items():
                btn.setChecked(s == scale)

    def update_position(self):
        """更新图形位置 - 修复：直接移动现有图形"""
        if self.canvas:
            x = self.x_input.value()
            y = self.y_input.value()
            self.canvas.update_shape_position(x, y)

    def update_rotation(self):
        """更新图形旋转角度"""
        if self.canvas:
            angle = self.rotation_input.value()
            self.canvas.update_shape_rotation(angle)

    def set_rotation(self, angle):
        """设置旋转角度"""
        self.rotation_input.setValue(angle)

    def confirm_requirement_description(self):
        """确认需求描述并调用大模型分析"""
        description = self.requirement_text.toPlainText().strip()
        if description:
            self.canvas.set_requirement_description(description)

            # 清空之前的输出
            self.model_output_text.clear()
            self.streaming_output_text.clear()
            self.training_text.clear()

            # 显示正在分析的状态
            self.model_output_text.setPlainText("正在调用大模型分析需求...")
            self.streaming_output_text.setPlainText("正在连接大模型...")

            # 显示进度条
            self.streaming_progress.setVisible(True)
            self.streaming_progress.setRange(0, 0)  # 不确定进度

            # 启用停止按钮，禁用确认按钮
            self.stop_generate_btn.setEnabled(True)
            self.confirm_btn.setEnabled(False)
            self.confirm_btn.setText("生成中...")

            # 重置停止标志
            self._should_stop_streaming = False

            QApplication.processEvents()

            try:
                # 获取当前选择的模型
                current_model = self.model_manager.get_current_model()
                if not current_model:
                    QMessageBox.warning(self, "警告", "请先选择模型")
                    self.reset_ui_state()
                    return

                # 重置流式输出状态
                self._streaming_output = ""
                self._is_streaming = True

                # 调用大模型（流式输出）
                success = self.call_llm_for_drawing_streaming(description)

                if success:
                    # 提取最终答案并显示到模型输出文本框
                    final_answer = self.extract_final_answer(self._streaming_output)
                    self.model_output_text.setPlainText(final_answer)
                    self.training_text.setPlainText(final_answer)
                    self.update_output_flow_text()

                    # 直接开始自动执行，不弹出确认窗口
                    self.center_label.setText("正在自动执行操作...")
                    QApplication.processEvents()

                    success_auto = self.execute_llm_instructions_from_text(final_answer)

                    if success_auto:
                        self.center_label.setText("自动执行完成")
                    else:
                        self.center_label.setText("自动执行失败")
                        QMessageBox.warning(self, "警告", "自动画图过程中出现错误")
                else:
                    if not self._should_stop_streaming:  # 如果不是用户主动停止
                        self.center_label.setText("大模型调用失败")
                        QMessageBox.warning(self, "警告", "大模型调用失败，请检查模型连接")

            except Exception as e:
                error_msg = f"调用大模型失败: {str(e)}"
                self.model_output_text.setPlainText(error_msg)
                self.streaming_output_text.append(f"\n错误: {error_msg}")
                QMessageBox.critical(self, "错误", error_msg)
            finally:
                self.reset_ui_state()
        else:
            QMessageBox.warning(self, "提示", "请输入需求描述")

    def stop_generation(self):
        """停止生成按钮点击事件"""
        if self._is_streaming:
            print("用户请求停止生成...")
            # 设置停止标志
            self._should_stop_streaming = True

            # 关闭流式请求
            if self._streaming_request:
                try:
                    self._streaming_request.close()
                    print("已关闭流式请求")
                except:
                    pass

            # 更新UI状态
            self.streaming_output_text.append("\n\n[用户已停止生成]")
            self.model_output_text.append("\n[生成已被用户停止]")

            # 重置UI状态
            self.reset_ui_state()

            # 添加已停止的状态显示
            self.center_label.setText("生成已停止")
            QApplication.processEvents()

            QMessageBox.information(self, "停止生成", "大模型生成已停止")

    def reset_ui_state(self):
        """重置UI状态"""
        self.confirm_btn.setEnabled(True)
        self.confirm_btn.setText("智能体画图")
        self.stop_generate_btn.setEnabled(False)  # 禁用停止按钮
        self.streaming_progress.setVisible(False)
        self._is_streaming = False
        self._streaming_request = None

    def call_llm_for_drawing_streaming(self, description):
        """调用大模型分析绘图需求（流式输出）"""
        try:
            # 系统提示词
            system_prompt = "现在你是智能绘图软件，图形选择有圆形、正方形、椭圆、矩形、三角形、五角星、直线、梯形，颜色有红色、黄色、蓝色、绿色、黑色、白色、" \
                            "粉色、紫色。要求根据描述输出画图的操作步骤。输出格式要严格遵守，输出格式例子：第1步，选择绘图工具为矩形；第2步，选择颜色为黑色；第3步，" \
                            "画一个矩形，调整图形位置到(406, 432)，设置宽度为160px，高度为143px；第4步，选择绘图工具为三角形；等等"

            full_prompt = f"{system_prompt}\n{description}"

            print(f"调用大模型，提示词: {full_prompt}")

            # 获取当前选择的模型
            current_model = self.model_manager.get_current_model()
            if not current_model:
                raise Exception("未选择模型")

            # 设置流式请求参数
            data = {
                "model": current_model,
                "prompt": full_prompt,
                "stream": True  # 启用流式输出
            }

            # 发送流式请求
            self._streaming_request = requests.post(self.OLLAMA_URL, json=data, stream=True, timeout=60)

            if self._streaming_request.status_code == 200:
                # 处理流式响应
                for line in self._streaming_request.iter_lines():
                    # 检查是否应该停止
                    if self._should_stop_streaming:
                        print("检测到停止标志，中断流式处理")
                        break

                    if line:
                        try:
                            # 解析JSON响应
                            json_line = json.loads(line.decode('utf-8'))
                            if 'response' in json_line:
                                chunk = json_line['response']
                                self._streaming_output += chunk

                                # 更新流式输出文本框
                                self.streaming_output_text.moveCursor(QTextCursor.End)
                                self.streaming_output_text.insertPlainText(chunk)
                                self.streaming_output_text.moveCursor(QTextCursor.End)
                                QApplication.processEvents()  # 强制更新UI

                                # 如果响应结束，显示最终响应
                                if json_line.get('done', False):
                                    print(f"大模型流式响应完成")
                                    break
                        except json.JSONDecodeError as e:
                            print(f"JSON解析错误: {e}")
                        except Exception as e:
                            print(f"处理流式响应错误: {e}")

                return True
            else:
                error_msg = f"请求失败: {self._streaming_request.status_code}"
                self.streaming_output_text.append(f"\n{error_msg}")
                return False

        except requests.exceptions.RequestException as e:
            if not self._should_stop_streaming:  # 如果不是用户主动停止导致的异常
                error_msg = f"网络错误: {str(e)}"
                self.streaming_output_text.append(f"\n{error_msg}")
                return False
            else:
                print("用户停止生成，请求异常是预期的")
                return False
        except Exception as e:
            if not self._should_stop_streaming:  # 如果不是用户主动停止导致的异常
                error_msg = f"大模型调用失败: {str(e)}"
                self.streaming_output_text.append(f"\n{error_msg}")
                return False
            else:
                print("用户停止生成，异常是预期的")
                return False

    def extract_final_answer(self, response):
        """从模型响应中提取</think>标签后面的内容"""
        if '</think>' in response:
            # 分割字符串，取</think>之后的部分
            parts = response.split('</think>', 1)
            if len(parts) > 1:
                final_answer = parts[1].strip()
                return final_answer
        # 如果没有找到</think>标签，返回原始响应
        return response.strip()

    def execute_llm_instructions_from_text(self, instruction_text):
        """根据大模型返回的文本自动执行绘图操作"""
        if not MOUSE_CONTROL_AVAILABLE:
            QMessageBox.warning(self, "功能不可用", "请先安装pyautogui: pip install pyautogui")
            return False

        try:
            # 解析大模型训练文本
            steps = self.parse_llm_training_text(instruction_text)
            if not steps:
                QMessageBox.warning(self, "错误", "无法解析大模型返回的操作步骤，请检查格式")
                return False

            # 执行操作步骤
            success = self.execute_steps_with_highlight(steps)

            return success

        except Exception as e:
            print(f"执行大模型指令错误: {e}")
            QMessageBox.critical(self, "错误", f"执行大模型指令失败: {str(e)}")
            return False

    def update_coordinates_display(self, x, y):
        """实时更新坐标显示"""
        if self.canvas and self.canvas.selected_shape_index >= 0:
            self.center_label.setText(f"中心点: ({x}, {y})")
        else:
            self.center_label.setText("中心点: 无选中图形")

    def start_recording(self):
        """开始记录操作 - 从0开始记录"""
        if not self.is_recording:
            self.is_recording = True
            self.operation_records = []  # 清空之前的记录
            self.record_start_time = time.time()

            # 重置记录状态变量
            self.last_tool = self.canvas.current_tool if self.canvas else "矩形"
            self.last_color = self.canvas.current_color if self.canvas else QColor(Qt.black)
            self.last_width = self.canvas.pen_width if self.canvas else 2
            self.last_scale = 1.0
            self.last_rotation = 0

            # 重置第一次绘图标志
            self.is_first_drawing = True

            # 立即记录初始的工具状态
            if self.is_recording:
                timestamp = 0.0  # 记录开始时间
                tool_record = {
                    'time': timestamp,
                    'type': 'tool_selection',
                    'tool': self.canvas.current_tool
                }
                self.operation_records.append(tool_record)
                self.last_tool = self.canvas.current_tool

                # 更新显示到训练文本
                training_text = f"第1步，选择绘图工具为{self.canvas.current_tool}；"
                self.training_text.setPlainText(training_text)

            # 更新UI状态
            self.start_record_btn.setEnabled(False)
            self.append_record_btn.setEnabled(False)  # 追加记录按钮在记录中禁用
            self.save_record_btn.setEnabled(True)
            self.record_status_label.setText("记录状态: 🔴 正在记录...")
            self.record_status_label.setStyleSheet(
                "color: #dc3545; font-weight: bold; background-color: #f8d7da; padding: 8px; border-radius: 3px; font-size: 12px;")

            # 为所有按钮添加事件监听
            self.setup_button_listeners()

            QMessageBox.information(self, "开始记录", "操作记录已开始！现在您的所有操作将被记录。")

    def append_recording(self):
        """追加记录操作 - 在原有记录基础上继续记录"""
        if not self.is_recording:
            self.is_recording = True

            # 如果之前没有记录，则初始化记录列表
            if not hasattr(self, 'operation_records') or self.operation_records is None:
                self.operation_records = []

            # 获取当前训练文本中的步骤数，用于确定起始时间
            current_training_text = self.training_text.toPlainText().strip()
            if current_training_text:
                # 计算现有步骤数
                steps = re.findall(r'第(\d+)步，', current_training_text)
                base_step_count = len(steps)
            else:
                base_step_count = 0

            # 设置记录开始时间（基于现有步骤的估算时间）
            self.record_start_time = time.time() - (base_step_count * 2)  # 假设每个步骤2秒

            # 设置当前状态变量
            self.last_tool = self.canvas.current_tool if self.canvas else "矩形"
            self.last_color = self.canvas.current_color if self.canvas else QColor(Qt.black)
            self.last_width = self.canvas.pen_width if self.canvas else 2
            self.last_scale = 1.0
            self.last_rotation = 0

            # 更新UI状态
            self.start_record_btn.setEnabled(False)
            self.append_record_btn.setEnabled(False)  # 追加记录按钮在记录中禁用
            self.save_record_btn.setEnabled(True)
            self.record_status_label.setText("记录状态: 🔴 正在追加记录...")
            self.record_status_label.setStyleSheet(
                "color: #dc3545; font-weight: bold; background-color: #f8d7da; padding: 8px; border-radius: 3px; font-size: 12px;")

            # 为所有按钮添加事件监听
            self.setup_button_listeners()

            QMessageBox.information(self, "追加记录", "操作记录追加已开始！现在您的所有操作将被追加到现有记录中。")

    def save_recording(self):
        """保存操作记录"""
        if self.is_recording:
            self.is_recording = False
            record_duration = time.time() - self.record_start_time

            # 更新UI状态
            self.start_record_btn.setEnabled(True)
            self.append_record_btn.setEnabled(True)  # 重新启用追加记录按钮
            self.save_record_btn.setEnabled(False)
            self.record_status_label.setText("记录状态: 已结束")
            self.record_status_label.setStyleSheet(
                "color: #28a745; font-weight: bold; background-color: #d4edda; padding: 8px; border-radius: 3px; font-size: 12px;")

            # 生成大模型训练文本
            self.generate_training_text()

            QMessageBox.information(self, "记录完成", f"操作记录已完成！共记录了 {len(self.operation_records)} 个操作步骤。")

    def generate_training_text(self):
        """生成大模型训练文本 - 修复：优化移动操作记录，只记录最终位置"""
        training_lines = []

        # 用于跟踪每个图形的最终位置
        shape_final_positions = {}
        processed_steps = []

        # 第一步：收集所有步骤，并优化移动操作
        for record in self.operation_records:
            if record['type'] == 'shape_drawing':
                # 记录绘制操作
                shape_key = f"{record['shape']}_{record['start_x']}_{record['start_y']}_{record['end_x']}_{record['end_y']}"
                center_x = (record['start_x'] + record['end_x']) // 2
                center_y = (record['start_y'] + record['end_y']) // 2
                shape_final_positions[shape_key] = {
                    'type': 'draw',
                    'shape': record['shape'],
                    'center_x': center_x,
                    'center_y': center_y,
                    'parameters': record.get('parameters', {})
                }
                processed_steps.append(('draw', shape_key, record))

            elif record['type'] == 'shape_movement':
                # 查找最近的相同类型的图形
                target_shape_key = None
                for shape_key, shape_data in shape_final_positions.items():
                    if shape_data['type'] == 'draw' and shape_data['shape'] == record['shape']:
                        target_shape_key = shape_key
                        break

                if target_shape_key:
                    # 更新图形的最终位置
                    shape_final_positions[target_shape_key]['center_x'] = record['center_x']
                    shape_final_positions[target_shape_key]['center_y'] = record['center_y']
                    processed_steps.append(('move', target_shape_key, record))
                else:
                    # 如果没有找到现有图形，创建新的绘制记录
                    shape_key = f"{record['shape']}_moved_{record['center_x']}_{record['center_y']}"
                    shape_final_positions[shape_key] = {
                        'type': 'draw',
                        'shape': record['shape'],
                        'center_x': record['center_x'],
                        'center_y': record['center_y'],
                        'parameters': {}  # 使用默认参数
                    }
                    processed_steps.append(('draw', shape_key, record))

            else:
                # 其他类型的操作直接添加
                processed_steps.append(('other', None, record))

        # 第二步：生成训练文本，只记录每个图形的最终位置
        step_counter = 1
        recorded_shapes = set()

        for step_type, shape_key, record in processed_steps:
            if step_type == 'other':
                # 处理其他类型的操作
                if record['type'] == 'tool_selection':
                    training_lines.append(f"第{step_counter}步，选择绘图工具为{record['tool']}；")
                    step_counter += 1
                elif record['type'] == 'color_selection':
                    training_lines.append(f"第{step_counter}步，选择颜色为{record['color']}；")
                    step_counter += 1
                elif record['type'] == 'width_selection':
                    training_lines.append(f"第{step_counter}步，选择线条粗细为{record['width']}px；")
                    step_counter += 1
                elif record['type'] == 'scale_selection':
                    scale_percent = int(record['scale'] * 100)
                    training_lines.append(f"第{step_counter}步，选择图形大小为{scale_percent}%；")
                    step_counter += 1
                elif record['type'] == 'rotation_change':
                    training_lines.append(f"第{step_counter}步，调整图形方向为{record['rotation']}度；")
                    step_counter += 1
                elif record['type'] == 'general_operation':
                    if record['operation'] == "清空画布":
                        training_lines.append(f"第{step_counter}步，清空画布；")
                        step_counter += 1
                    elif record['operation'] == "保存绘图":
                        training_lines.append(f"第{step_counter}步，保存绘图；")
                        step_counter += 1
                    elif record['operation'] == "确认需求描述":
                        training_lines.append(f"第{step_counter}步，确认需求描述并开始自动绘图；")
                        step_counter += 1

            elif step_type == 'draw' and shape_key not in recorded_shapes:
                # 只记录每个图形的最终位置
                shape_data = shape_final_positions[shape_key]
                shape_info = f"画一个{shape_data['shape']}，调整图形位置到({shape_data['center_x']}, {shape_data['center_y']})"

                # 添加参数信息
                params = shape_data.get('parameters', {})
                if shape_data['shape'] == "矩形":
                    width = params.get('width', '')
                    height = params.get('height', '')
                    if width and height:
                        shape_info += f"，设置宽度为{width}px，高度为{height}px"
                elif shape_data['shape'] == "正方形":
                    side = params.get('side', '')
                    if side:
                        shape_info += f"，设置边长为{side}px"
                elif shape_data['shape'] == "圆形":
                    radius = params.get('radius', '')
                    if radius:
                        shape_info += f"，设置半径为{radius}px"
                elif shape_data['shape'] == "椭圆":
                    major = params.get('major', '')
                    minor = params.get('minor', '')
                    if major and minor:
                        shape_info += f"，设置长轴为{major}px，短轴为{minor}px"
                elif shape_data['shape'] == "三角形":
                    base = params.get('base', '')
                    height_val = params.get('height', '')
                    if base and height_val:
                        shape_info += f"，设置底边为{base}px，高度为{height_val}px"
                elif shape_data['shape'] == "五角星":
                    size = params.get('size', '')
                    if size:
                        shape_info += f"，设置大小为{size}px"
                elif shape_data['shape'] == "直线":
                    length = params.get('length', '')
                    if length:
                        shape_info += f"，设置长度为{length}px"
                elif shape_data['shape'] == "梯形":
                    top_base = params.get('top_base', '')
                    bottom_base = params.get('bottom_base', '')
                    height_val = params.get('height', '')
                    if top_base and bottom_base and height_val:
                        shape_info += f"，设置上底为{top_base}px，下底为{bottom_base}px，高度为{height_val}px"

                training_lines.append(f"第{step_counter}步，{shape_info}；")
                recorded_shapes.add(shape_key)
                step_counter += 1

        training_text = "".join(training_lines)
        if training_text.endswith("；"):
            training_text = training_text[:-1] + "。"

        # 设置文本并更新步骤编号
        self.training_text.blockSignals(True)
        self.training_text.setPlainText(training_text)
        self.training_text.blockSignals(False)

        # 同时更新输出流程文本
        self.update_output_flow_text()

    def setup_button_listeners(self):
        """为所有按钮设置操作记录监听"""
        for tool_name, button in self.tool_buttons.items():
            button.clicked.connect(lambda checked, tool=tool_name: self.record_tool_selection(tool))

        for color_name, button in self.color_buttons.items():
            button.clicked.connect(lambda checked, color=color_name: self.record_color_selection(color))

        for width, button in self.width_buttons.items():
            button.clicked.connect(lambda checked, w=width: self.record_width_selection(w))

        for scale, button in self.scale_buttons.items():
            button.clicked.connect(lambda checked, s=scale: self.record_scale_selection(s))

        self.clear_btn.clicked.connect(lambda: self.record_general_operation("清空画布"))
        self.save_btn.clicked.connect(lambda: self.record_general_operation("保存绘图"))
        self.confirm_btn.clicked.connect(lambda: self.record_general_operation("确认需求描述"))

    def record_tool_selection(self, tool_name):
        """记录工具选择操作"""
        if self.is_recording and tool_name != self.last_tool:
            timestamp = time.time() - self.record_start_time
            record = {
                'time': timestamp,
                'type': 'tool_selection',
                'tool': tool_name
            }
            self.operation_records.append(record)
            self.last_tool = tool_name

            # 更新训练文本
            self.generate_training_text()

    def record_color_selection(self, color_name):
        """记录颜色选择操作"""
        if self.is_recording:
            color = self.color_map[color_name]
            if color != self.last_color:
                timestamp = time.time() - self.record_start_time
                record = {
                    'time': timestamp,
                    'type': 'color_selection',
                    'color': color_name
                }
                self.operation_records.append(record)
                self.last_color = color

                # 更新训练文本
                self.generate_training_text()

    def record_width_selection(self, width):
        """记录线条粗细选择操作"""
        if self.is_recording and width != self.last_width:
            timestamp = time.time() - self.record_start_time
            record = {
                'time': timestamp,
                'type': 'width_selection',
                'width': width
            }
            self.operation_records.append(record)
            self.last_width = width

            # 更新训练文本
            self.generate_training_text()

    def record_scale_selection(self, scale):
        """记录缩放选择操作"""
        if self.is_recording and scale != self.last_scale:
            timestamp = time.time() - self.record_start_time
            record = {
                'time': timestamp,
                'type': 'scale_selection',
                'scale': scale
            }
            self.operation_records.append(record)
            self.last_scale = scale

            # 更新训练文本
            self.generate_training_text()

    def record_rotation_change(self, rotation):
        """记录旋转变化操作"""
        if self.is_recording and rotation != self.last_rotation:
            timestamp = time.time() - self.record_start_time
            record = {
                'time': timestamp,
                'type': 'rotation_change',
                'rotation': rotation
            }
            self.operation_records.append(record)
            self.last_rotation = rotation

            # 更新训练文本
            self.generate_training_text()

    def record_shape_drawing(self, shape_type, start_x, start_y, end_x, end_y):
        """记录形状绘制操作"""
        if self.is_recording:
            timestamp = time.time() - self.record_start_time

            # 关键修复：从最新添加的形状中获取参数，而不是从选中的形状中获取
            parameters = {}
            if self.canvas.shapes:  # 确保有形状
                # 获取最后一个添加的形状（刚刚绘制的）
                last_shape = self.canvas.shapes[-1]
                if last_shape.get('type') == 'shape' and last_shape.get('shape') == shape_type:
                    parameters = last_shape.get('parameters', {})
                    print(f"记录形状绘制 - 形状: {shape_type}, 参数: {parameters}")  # 调试信息

            # 记录形状绘制
            record = {
                'time': timestamp,
                'type': 'shape_drawing',
                'shape': shape_type,
                'start_x': start_x,
                'start_y': start_y,
                'end_x': end_x,
                'end_y': end_y,
                'parameters': parameters.copy()  # 保存参数
            }
            self.operation_records.append(record)

            # 更新训练文本
            self.generate_training_text()

    def record_shape_movement(self, shape_type, center_x, center_y):
        """记录形状移动操作"""
        if self.is_recording and self.canvas.selected_shape_index >= 0:
            timestamp = time.time() - self.record_start_time

            # 记录形状移动
            record = {
                'time': timestamp,
                'type': 'shape_movement',
                'shape': shape_type,
                'center_x': center_x,
                'center_y': center_y
            }
            self.operation_records.append(record)

            # 更新训练文本
            self.generate_training_text()

    def record_general_operation(self, operation_name):
        """记录一般操作"""
        if self.is_recording:
            timestamp = time.time() - self.record_start_time
            record = {
                'time': timestamp,
                'type': 'general_operation',
                'operation': operation_name
            }
            self.operation_records.append(record)

            # 更新训练文本
            self.generate_training_text()

    def update_step_numbers_in_training_text(self):
        """自动更新大模型训练文本中的步骤编号"""
        training_text = self.training_text.toPlainText().strip()
        if not training_text:
            return

        # 使用正则表达式匹配所有步骤
        steps = re.findall(r'第(\d+)步，(.+?)(?=；|$)', training_text)

        if not steps:
            return

        # 重新构建文本，更新步骤编号
        new_training_text = ""
        for i, (old_num, step_content) in enumerate(steps, 1):
            new_training_text += f"第{i}步，{step_content}；"

        # 移除最后一个分号，改为句号
        if new_training_text.endswith("；"):
            new_training_text = new_training_text[:-1] + "。"

        # 更新文本框（避免触发信号循环）
        self.training_text.blockSignals(True)
        self.training_text.setPlainText(new_training_text)
        self.training_text.blockSignals(False)

        # 同时更新输出流程文本
        self.update_output_flow_text()

    def update_output_flow_text(self):
        """更新大模型输出流程文本 - 修复：确保每行一个步骤，始终保持格式"""
        training_text = self.training_text.toPlainText().strip()
        if not training_text:
            self.output_flow_text.setPlainText("")
            return

        # 使用正则表达式匹配所有步骤
        steps = re.findall(r'第(\d+)步，(.+?)(?=；|$)', training_text)

        if not steps:
            return

        # 构建格式化文本，每行一个步骤，保留第几步
        formatted_text = ""
        for i, (step_num, step_content) in enumerate(steps, 1):
            # 确保每个步骤以句号结束
            if not step_content.endswith('。'):
                step_content += '。'
            formatted_text += f"第{i}步，{step_content}\n"

        # 关键修复：始终使用setPlainText确保格式不变
        self.output_flow_text.setPlainText(formatted_text.strip())

    def highlight_current_step(self, step_index):
        """高亮显示当前正在执行的步骤"""
        if step_index < 0:
            # 重置所有步骤颜色，使用纯文本格式
            self.output_flow_text.setStyleSheet("")
            self.update_output_flow_text()  # 重新设置格式
            return

        training_text = self.training_text.toPlainText().strip()
        if not training_text:
            return

        # 获取所有步骤
        steps = re.findall(r'第(\d+)步，(.+?)(?=；|$)', training_text)
        if step_index >= len(steps):
            return

        # 构建带高亮的文本
        formatted_text = ""
        for i, (step_num, step_content) in enumerate(steps):
            if not step_content.endswith('。'):
                step_content += '。'

            if i == step_index:
                # 当前步骤使用特殊样式
                formatted_text += f'<span style="background-color: #ffeb3b; color: #000; font-weight: bold;">第{i + 1}步，{step_content}</span>\n'
            else:
                formatted_text += f"第{i + 1}步，{step_content}\n"

        # 使用HTML格式设置文本
        self.output_flow_text.setHtml(formatted_text.strip())

    def on_training_text_changed(self):
        """当大模型训练文本发生变化时自动更新步骤编号"""
        # 使用定时器延迟执行，避免在文本变化过程中频繁触发
        self._text_change_timer.start(500)  # 500ms后执行
        self._output_flow_timer.start(600)  # 600ms后更新输出流程

    def execute_llm_instructions(self):
        """根据大模型训练文本自动执行绘图操作"""
        if not MOUSE_CONTROL_AVAILABLE:
            QMessageBox.warning(self, "功能不可用", "请先安装pyautogui: pip install pyautogui")
            return

        training_text = self.training_text.toPlainText().strip()
        if not training_text:
            QMessageBox.warning(self, "提示", "大模型训练文本为空，请先生成或输入操作步骤")
            return

        try:
            # 解析大模型训练文本
            steps = self.parse_llm_training_text(training_text)
            if not steps:
                QMessageBox.warning(self, "错误", "无法解析大模型训练文本，请检查格式")
                return

            # 直接开始执行，不弹出确认窗口
            self.center_label.setText("正在根据大模型画图...")
            QApplication.processEvents()

            # 执行操作步骤
            success = self.execute_steps_with_highlight(steps)

            if success:
                self.center_label.setText("大模型画图完成")
            else:
                self.center_label.setText("大模型画图失败")

        except Exception as e:
            print(f"执行大模型指令错误: {e}")
            QMessageBox.critical(self, "错误", f"执行大模型指令失败: {str(e)}")

    def execute_steps_with_highlight(self, steps):
        """执行操作步骤并高亮显示当前步骤 - 修复：直接绘制到最终位置，不进行移动"""
        try:
            # 重置画布状态
            self.canvas.drawing = False
            self.canvas.dragging = False
            self.canvas.current_path = None
            self.canvas.is_freehand_drawing = False
            self.canvas.freehand_points = []

            # 清空画布
            self.canvas.clear_canvas()

            for step_index, step in enumerate(steps):
                # 高亮显示当前步骤
                self.current_step_index = step_index
                self.highlight_current_step(step_index)
                QApplication.processEvents()

                step_type = step.get('type')

                if step_type == 'select_tool':
                    # 选择工具
                    tool = step['tool']
                    if tool in self.tool_buttons:
                        button = self.tool_buttons[tool]
                        button_global_pos = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
                        pyautogui.moveTo(button_global_pos.x(), button_global_pos.y(), duration=0.5)
                        time.sleep(0.5)
                        pyautogui.click()
                        time.sleep(0.5)
                        self.canvas.current_tool = tool
                        print(f"选择工具: {tool}")

                elif step_type == 'select_color':
                    # 选择颜色
                    color_name = step['color']
                    if color_name in self.color_buttons:
                        button = self.color_buttons[color_name]
                        button_global_pos = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
                        pyautogui.moveTo(button_global_pos.x(), button_global_pos.y(), duration=0.5)
                        time.sleep(0.5)
                        pyautogui.click()
                        time.sleep(0.5)
                        self.canvas.current_color = self.color_map[color_name]
                        print(f"选择颜色: {color_name}")

                elif step_type == 'select_width':
                    # 选择线条粗细
                    width = step['width']
                    if width in self.width_buttons:
                        button = self.width_buttons[width]
                        button_global_pos = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
                        pyautogui.moveTo(button_global_pos.x(), button_global_pos.y(), duration=0.5)
                        time.sleep(0.5)
                        pyautogui.click()
                        time.sleep(0.5)
                        self.canvas.pen_width = width
                        print(f"选择线条粗细: {width}px")

                elif step_type == 'draw_shape':
                    # 绘制图形 - 直接绘制到最终位置，使用正确的参数
                    shape = step['shape']
                    center_x = step['x']
                    center_y = step['y']
                    parameters = step.get('parameters', {})

                    print(f"执行绘制: {shape} 在 ({center_x}, {center_y}), 参数: {parameters}")  # 调试信息

                    # 根据参数计算正确的起点和终点
                    if shape == "矩形":
                        width = parameters.get('width', 100)
                        height = parameters.get('height', 80)
                        start_x = center_x - width // 2
                        start_y = center_y - height // 2
                        end_x = center_x + width // 2
                        end_y = center_y + height // 2
                    elif shape == "正方形":
                        side = parameters.get('side', 100)
                        start_x = center_x - side // 2
                        start_y = center_y - side // 2
                        end_x = center_x + side // 2
                        end_y = center_y + side // 2
                    elif shape == "圆形":
                        radius = parameters.get('radius', 50)
                        start_x = center_x - radius
                        start_y = center_y - radius
                        end_x = center_x + radius
                        end_y = center_y + radius
                    elif shape == "椭圆":
                        major = parameters.get('major', 120)
                        minor = parameters.get('minor', 80)
                        start_x = center_x - major // 2
                        start_y = center_y - minor // 2
                        end_x = center_x + major // 2
                        end_y = center_y + minor // 2
                    elif shape == "三角形":
                        base = parameters.get('base', 100)
                        height_val = parameters.get('height', 80)
                        start_x = center_x - base // 2
                        start_y = center_y + height_val // 2
                        end_x = center_x + base // 2
                        end_y = center_y - height_val // 2
                    elif shape == "五角星":
                        size = parameters.get('size', 80)
                        start_x = center_x - size // 2
                        start_y = center_y - size // 2
                        end_x = center_x + size // 2
                        end_y = center_y + size // 2
                    elif shape == "直线":
                        length = parameters.get('length', 100)
                        start_x = center_x - length // 2
                        start_y = center_y
                        end_x = center_x + length // 2
                        end_y = center_y
                    elif shape == "梯形":
                        top_base = parameters.get('top_base', 60)
                        bottom_base = parameters.get('bottom_base', 100)
                        height_val = parameters.get('height', 80)
                        start_x = center_x - bottom_base // 2
                        start_y = center_y + height_val // 2
                        end_x = center_x + bottom_base // 2
                        end_y = center_y - height_val // 2
                    else:
                        # 默认情况
                        start_x, start_y = center_x - 50, center_y - 50
                        end_x, end_y = center_x + 50, center_y + 50

                    # 关键修复：直接添加形状到画布，使用正确的参数
                    start_point = QPoint(int(start_x), int(start_y))
                    end_point = QPoint(int(end_x), int(end_y))
                    self.canvas.add_shape_directly(shape, start_point, end_point, parameters)

                    # 强制更新画布显示
                    self.canvas.update()
                    QApplication.processEvents()
                    time.sleep(0.5)  # 给一点时间显示

                    print(f"绘制{shape}: 位置({center_x}, {center_y})，参数{parameters}")

            # 重置高亮
            self.current_step_index = -1
            self.highlight_current_step(-1)

            return True

        except Exception as e:
            print(f"执行步骤错误: {e}")
            # 重置高亮
            self.current_step_index = -1
            self.highlight_current_step(-1)

            return False

    def parse_llm_training_text(self, training_text):
        """解析大模型训练文本，提取操作步骤 - 修复：正确解析移动操作"""
        steps = []

        # 使用分号或"第几步"来分割步骤
        # 先尝试按分号分割
        if "；" in training_text:
            raw_steps = training_text.split("；")
        else:
            # 如果没有分号，尝试按"第几步"分割
            raw_steps = re.split(r'第\d+步，', training_text)
            # 移除第一个空字符串（如果有）
            if raw_steps and not raw_steps[0]:
                raw_steps = raw_steps[1:]

        for i, step_text in enumerate(raw_steps):
            step_text = step_text.strip()
            if not step_text:
                continue

            # 移除末尾的句号或分号
            if step_text.endswith('。') or step_text.endswith('；'):
                step_text = step_text[:-1]

            # 解析步骤类型
            step_info = self.parse_step(step_text)
            if step_info:
                steps.append(step_info)

        return steps

    def parse_step(self, step_text):
        """解析单个步骤文本"""
        step_text = step_text.strip()

        # 选择绘图工具
        if "选择绘图工具为" in step_text:
            tool_match = re.search(r'选择绘图工具为(\S+)', step_text)
            if tool_match:
                tool = tool_match.group(1)
                return {'type': 'select_tool', 'tool': tool}

        # 选择颜色
        elif "选择颜色为" in step_text:
            color_match = re.search(r'选择颜色为(\S+)', step_text)
            if color_match:
                color = color_match.group(1)
                return {'type': 'select_color', 'color': color}

        # 选择线条粗细
        elif "选择线条粗细为" in step_text:
            width_match = re.search(r'选择线条粗细为(\d+)px', step_text)
            if width_match:
                width = int(width_match.group(1))
                return {'type': 'select_width', 'width': width}

        # 画图形（带参数）- 关键修复：直接解析最终位置
        elif "画一个" in step_text and "调整图形位置到" in step_text:
            # 提取图形类型
            shape_match = re.search(r'画一个(\S+)，调整图形位置到', step_text)
            if shape_match:
                shape = shape_match.group(1)
                # 提取坐标
                coord_match = re.search(r'调整图形位置到\((\d+),\s*(\d+)\)', step_text)
                if coord_match:
                    x = int(coord_match.group(1))
                    y = int(coord_match.group(2))

                    # 提取参数
                    parameters = {}
                    if shape == "矩形":
                        width_match = re.search(r'设置宽度为(\d+)px', step_text)
                        height_match = re.search(r'高度为(\d+)px', step_text)
                        if width_match and height_match:
                            parameters = {
                                'width': int(width_match.group(1)),
                                'height': int(height_match.group(1))
                            }
                    elif shape == "正方形":
                        side_match = re.search(r'设置边长为(\d+)px', step_text)
                        if side_match:
                            parameters = {'side': int(side_match.group(1))}
                    elif shape == "圆形":
                        radius_match = re.search(r'设置半径为(\d+)px', step_text)
                        if radius_match:
                            parameters = {'radius': int(radius_match.group(1))}
                    elif shape == "椭圆":
                        major_match = re.search(r'设置长轴为(\d+)px', step_text)
                        minor_match = re.search(r'短轴为(\d+)px', step_text)
                        if major_match and minor_match:
                            parameters = {
                                'major': int(major_match.group(1)),
                                'minor': int(minor_match.group(1))
                            }
                    elif shape == "三角形":
                        base_match = re.search(r'设置底边为(\d+)px', step_text)
                        height_match = re.search(r'高度为(\d+)px', step_text)
                        if base_match and height_match:
                            parameters = {
                                'base': int(base_match.group(1)),
                                'height': int(height_match.group(1))
                            }
                    elif shape == "五角星":
                        size_match = re.search(r'设置大小为(\d+)px', step_text)
                        if size_match:
                            parameters = {'size': int(size_match.group(1))}
                    elif shape == "直线":
                        length_match = re.search(r'设置长度为(\d+)px', step_text)
                        if length_match:
                            parameters = {'length': int(length_match.group(1))}
                    elif shape == "梯形":
                        top_match = re.search(r'设置上底为(\d+)px', step_text)
                        bottom_match = re.search(r'下底为(\d+)px', step_text)
                        height_match = re.search(r'高度为(\d+)px', step_text)
                        if top_match and bottom_match and height_match:
                            parameters = {
                                'top_base': int(top_match.group(1)),
                                'bottom_base': int(bottom_match.group(1)),
                                'height': int(height_match.group(1))
                            }

                    return {'type': 'draw_shape', 'shape': shape, 'x': x, 'y': y, 'parameters': parameters}

        return None

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