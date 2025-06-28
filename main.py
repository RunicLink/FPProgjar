import pygame
import sys
import json
import time
import socket
import math 

WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 800
BOARD_SIZE, CELL_SIZE, BOARD_MARGIN = 10, 40, 50
WHITE, BLACK, BLUE, RED, GREEN, GRAY, LIGHT_GRAY = (255, 255, 255), (0, 0, 0), (0, 100, 200), (200, 0, 0), (0, 200, 0), (128, 128, 128), (200, 200, 200)
ORANGE = (255, 165, 0)

DARK_BLUE = (25, 50, 100)
LIGHT_BLUE = (173, 216, 230)
NAVY_BLUE = (0, 0, 128)
GOLD = (255, 215, 0)
SILVER = (192, 192, 192)
DARK_GREEN = (0, 100, 0)
LIGHT_GREEN = (144, 238, 144)
CRIMSON = (220, 20, 60)
DEEP_GRAY = (64, 64, 64)
SOFT_WHITE = (248, 248, 255)
GRADIENT_START = (45, 85, 135)
GRADIENT_END = (25, 50, 100)

class BattleshipHttpClient:
    def __init__(self, host='localhost', port=8889):
        self.host = host
        self.port = port
        self.game_id = None
        self.player_number = None
        self.player_name = None
        self.message_callbacks = []
        self.last_successful_poll = time.time()
        self.sock = None 
        self.is_spectator = False 

    def connect(self):
        if self.sock: 
            self.disconnect()
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            print("Successfully connected to the server.")
        except Exception as e:
            print(f"Failed to connect: {e}")
            self.sock = None
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}")

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        print("Disconnected from the server.")

    def add_message_callback(self, callback):
        self.message_callbacks.append(callback)

    def _send_request(self, method, path, payload=None):
        if not self.sock:
            try:
                self.connect()
            except ConnectionError as e:
                print(f"Connection failed: {e}")
                self._notify_listeners({'type': 'disconnect_error', 'message': f'Connection lost: {e}'})
                return None

        try:
            body = json.dumps(payload) if payload else ''
            request = (
                f"{method} {path} HTTP/1.0\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: keep-alive\r\n\r\n"
                f"{body}"
            )
            self.sock.sendall(request.encode('utf-8'))

            response_data = b''
            while b'\r\n\r\n' not in response_data:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Server closed the connection unexpectedly.")
                response_data += chunk
            
            header_part, body_part = response_data.split(b'\r\n\r\n', 1)

            headers = {}
            for line in header_part.decode('utf-8').split('\r\n')[1:]:
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    headers[key.lower()] = value

            content_length = int(headers.get('content-length', 0))
            
            while len(body_part) < content_length:
                chunk = self.sock.recv(content_length - len(body_part))
                if not chunk:
                    raise ConnectionError("Incomplete response from server.")
                body_part += chunk
                
            self.last_successful_poll = time.time()
            return json.loads(body_part.decode('utf-8'))

        except (ConnectionError, ConnectionResetError, BrokenPipeError, socket.timeout) as e:
            print(f"HTTP request to {path} failed due to connection issue: {e}")
            self._notify_listeners({'type': 'disconnect_error', 'message': f'Connection lost: {e}'})
            self.disconnect() 
            return None
        except Exception as e:
            print(f"An unexpected error occurred during request to {path}: {e}")
            self._notify_listeners({'type': 'error', 'message': f'Request failed: {e}'})
            self.disconnect()
            return None

    def host_game(self, player_name):
        self.player_name = player_name
        self.is_spectator = False 
        response = self._send_request('POST', '/api/host', {'player_name': player_name})
        if response and 'game_id' in response:
            self.game_id = response['game_id']
            self.player_number = response['player_number']
            self.get_game_state()
        else:
            self._notify_listeners({'type': 'error', 'message': 'Could not host game.'})

    def join_private_game(self, player_name, room_code):
        self.player_name = player_name
        self.is_spectator = False 
        response = self._send_request('POST', '/api/join', {'player_name': player_name, 'game_id': room_code})
        if response and 'player_number' in response:
            self.game_id = room_code
            self.player_number = response['player_number']
            self.get_game_state()
        elif response:
            error_msg = response.get('error', 'Could not join game.')
            self._notify_listeners({'type': 'room_join_status', 'success': False, 'message': error_msg})

    def reconnect(self):
        if not self.player_name and not self.is_spectator or not self.game_id:
            return
        if self.is_spectator:
            response = self._send_request('POST', '/api/spectate', {'game_id': self.game_id})
        else:
            response = self._send_request('POST', '/api/reconnect', {'player_name': self.player_name, 'game_id': self.game_id})

        if response and response.get('reconnected'):
            self._notify_listeners({'type': 'reconnect_success'})
            self.get_game_state()
        else:
            self._notify_listeners({'type': 'error', 'message': 'Reconnect failed.'})


    def place_ships(self, ships_data):
        payload = {'game_id': self.game_id, 'player_number': self.player_number, 'ships': ships_data}
        response = self._send_request('POST', '/api/place_ships', payload)
        if response:
            self._notify_listeners({'type': 'ships_placed', 'success': True})
            self.get_game_state()
        else:
            self._notify_listeners({'type': 'ships_placed', 'success': False, 'message': 'Failed to place ships.'})
            
    def attack(self, row, col):
        payload = {'game_id': self.game_id, 'player_number': self.player_number, 'row': row, 'col': col}
        self._send_request('POST', '/api/attack', payload)
        self.get_game_state()

    def get_game_state(self):
        if not self.game_id or (self.player_number is None and not self.is_spectator): 
            return
        path = f"/api/gamestate?game_id={self.game_id}"
        if not self.is_spectator:
            path += f"&player_number={self.player_number}"
        else:
            path += f"&is_spectator=true" 
            
        response = self._send_request('GET', path)
        if response:
            self._notify_listeners(response)

    def quick_match(self, player_name):
        self.game_id = None
        self.player_number = None
        self.player_name = player_name
        self.is_spectator = False 
        
        print(f"DEBUG: Starting quick match for {player_name}")
        response = self._send_request('POST', '/api/quick_match', {'player_name': player_name})
        print(f"DEBUG: Quick match response: {response}")
        
        if response:
            if response.get('matched'):
                self.game_id = response['game_id']
                self.player_number = response['player_number']
                print(f"DEBUG: Match found immediately! Game ID: {self.game_id}, Player: {self.player_number}")
                self._notify_listeners({
                    'type': 'quick_match_found',
                    'opponent_name': response['opponent_name']
                })
                self.get_game_state()
            else:
                print("DEBUG: Waiting for opponent")
                self._notify_listeners({'type': 'quick_match_waiting'})
        else:
            print("DEBUG: Quick match request failed")
            self._notify_listeners({'type': 'error', 'message': 'Could not start quick match.'})

    def cancel_quick_match(self):
        if not self.player_name:
            return
        response = self._send_request('POST', '/api/cancel_quick_match', {'player_name': self.player_name})
        if response and response.get('cancelled'):
            self._notify_listeners({'type': 'quick_match_cancelled'})
        else:
            self._notify_listeners({'type': 'error', 'message': 'Could not cancel quick match.'})

    def check_quick_match_status(self):
        if not self.player_name:
            return
        
        print(f"DEBUG: Checking quick match status for {self.player_name}")
        response = self._send_request('POST', '/api/check_quick_match', {'player_name': self.player_name})
        print(f"DEBUG: Quick match status response: {response}")
        
        if response:
            if response.get('matched'):
                self.game_id = response['game_id']
                self.player_number = response['player_number']
                print(f"DEBUG: Match found! Game ID: {self.game_id}, Player: {self.player_number}")
                self._notify_listeners({
                    'type': 'quick_match_found',
                    'opponent_name': response['opponent_name']
                })
                self.get_game_state()
            elif response.get('waiting'):
                print("DEBUG: Still waiting for opponent")
                pass
        else:
            print("DEBUG: No longer in queue, cancelling")
            self._notify_listeners({'type': 'quick_match_cancelled'})

    def get_ongoing_quick_matches(self):
        response = self._send_request('GET', '/api/quick_matches')
        if response:
            self._notify_listeners({'type': 'ongoing_matches', 'matches': response.get('matches', [])})
        else:
            self._notify_listeners({'type': 'error', 'message': 'Could not fetch ongoing matches.'})

    def spectate_game(self, game_id):
        self.game_id = game_id
        self.player_number = None 
        self.player_name = "Spectator" 
        self.is_spectator = True
        response = self._send_request('POST', '/api/spectate', {'game_id': game_id})
        if response and response.get('success'):
            self._notify_listeners({'type': 'spectate_success'})
            self.get_game_state()
        else:
            self._notify_listeners({'type': 'error', 'message': 'Could not spectate game.'})

    def _notify_listeners(self, message):
        for callback in self.message_callbacks:
            callback(message)

pygame.init()

class EnhancedInputBox:
    def __init__(self, x, y, w, h, text='', placeholder=''):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = DEEP_GRAY
        self.text = text
        self.placeholder = placeholder
        self.font = pygame.font.Font(None, 32)
        self.small_font = pygame.font.Font(None, 26)
        self.active = False
        self.txt_surface = self.font.render(text, True, self.color)
        self.cursor_visible = True
        self.cursor_timer = 0
        self.border_radius = 10
        self.shadow_offset = 3

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = not self.active
            else:
                self.active = False
            self.color = DARK_BLUE if self.active else DEEP_GRAY
        if event.type == pygame.KEYDOWN:
            if self.active:
                if event.key == pygame.K_RETURN:
                    self.active = False
                    self.color = DEEP_GRAY
                    return True
                elif event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                else:
                    self.text += event.unicode
                self.txt_surface = self.font.render(self.text, True, self.color)
        return False

    def update(self):
        self.cursor_timer += 1
        if self.cursor_timer >= 30:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0

    def draw(self, screen):
        shadow_rect = self.rect.copy()
        shadow_rect.x += self.shadow_offset
        shadow_rect.y += self.shadow_offset
        pygame.draw.rect(screen, (0, 0, 0, 50), shadow_rect, border_radius=self.border_radius)
        
        bg_color = SOFT_WHITE if self.active else LIGHT_GRAY
        pygame.draw.rect(screen, bg_color, self.rect, border_radius=self.border_radius)
        
        border_color = DARK_BLUE if self.active else DEEP_GRAY
        border_width = 3 if self.active else 2
        pygame.draw.rect(screen, border_color, self.rect, border_width, border_radius=self.border_radius)
        
        if self.text:
            screen.blit(self.txt_surface, (self.rect.x + 15, self.rect.y + (self.rect.height - self.txt_surface.get_height()) // 2))
        elif not self.active and self.placeholder:
            placeholder_surface = self.small_font.render(self.placeholder, True, GRAY)
            screen.blit(placeholder_surface, (self.rect.x + 15, self.rect.y + (self.rect.height - placeholder_surface.get_height()) // 2))
        
        if self.active and self.cursor_visible and self.text:
            cursor_x = self.rect.x + 15 + self.txt_surface.get_width() + 2
            cursor_y = self.rect.y + 8
            pygame.draw.line(screen, self.color, (cursor_x, cursor_y), (cursor_x, cursor_y + self.rect.height - 16), 2)

    def get_text(self):
        return self.text

class EnhancedButton:
    def __init__(self, x, y, w, h, text, color, hover_color, action=None, icon=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.current_color = color
        self.action = action
        self.icon = icon
        self.font = pygame.font.Font(None, 36)
        self.text_surface = self.font.render(text, True, WHITE)
        self.text_rect = self.text_surface.get_rect(center=self.rect.center)
        self.border_radius = 12
        self.shadow_offset = 4
        self.pressed = False
        self.hover_animation = 0
        self.glow_effect = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            if self.rect.collidepoint(event.pos):
                self.current_color = self.hover_color
                self.hover_animation = min(self.hover_animation + 2, 10)
                self.glow_effect = min(self.glow_effect + 3, 15)
            else:
                self.current_color = self.color
                self.hover_animation = max(self.hover_animation - 2, 0)
                self.glow_effect = max(self.glow_effect - 3, 0)
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
        
        if event.type == pygame.MOUSEBUTTONUP:
            if self.rect.collidepoint(event.pos) and self.pressed:
                if self.action:
                    self.action()
                    self.pressed = False
                    return True
            self.pressed = False
        return False

    def draw(self, screen):
        button_rect = self.rect.copy()
        if self.hover_animation > 0:
            button_rect.y -= self.hover_animation // 2
        
        if self.pressed:
            button_rect.y += 2
        
        if self.glow_effect > 0:
            glow_rect = button_rect.inflate(self.glow_effect * 2, self.glow_effect * 2)
            glow_surface = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
            glow_color = (*self.hover_color[:3], 30)
            pygame.draw.rect(glow_surface, glow_color, glow_surface.get_rect(), border_radius=self.border_radius + 5)
            screen.blit(glow_surface, glow_rect.topleft)
        
        if not self.pressed:
            shadow_rect = button_rect.copy()
            shadow_rect.x += self.shadow_offset
            shadow_rect.y += self.shadow_offset
            shadow_surface = pygame.Surface((shadow_rect.width, shadow_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(shadow_surface, (0, 0, 0, 100), shadow_surface.get_rect(), border_radius=self.border_radius)
            screen.blit(shadow_surface, shadow_rect.topleft)
        
        self._draw_gradient_rect(screen, button_rect, self.current_color)
        
        pygame.draw.rect(screen, WHITE, button_rect, 2, border_radius=self.border_radius)
        
        text_rect = self.text_surface.get_rect(center=button_rect.center)
        screen.blit(self.text_surface, text_rect)

    def _draw_gradient_rect(self, screen, rect, base_color):
        lighter_color = tuple(min(255, c + 30) for c in base_color)
        darker_color = tuple(max(0, c - 30) for c in base_color)
        
        for y in range(rect.height):
            progress = y / rect.height
            color = tuple(
                int(lighter_color[i] * (1 - progress) + darker_color[i] * progress)
                for i in range(3)
            )
            line_rect = pygame.Rect(rect.x, rect.y + y, rect.width, 1)
            pygame.draw.rect(screen, color, line_rect)
        
        mask_surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask_surface, (255, 255, 255, 255), mask_surface.get_rect(), border_radius=self.border_radius)
        
        temp_surface = screen.subsurface(rect).copy()
        temp_surface.blit(mask_surface, (0,0), None, pygame.BLEND_RGBA_MULT)
        screen.blit(temp_surface, rect.topleft)

def draw_animated_background(screen, time_offset=0):
    for y in range(WINDOW_HEIGHT):
        progress = y / WINDOW_HEIGHT
        color = tuple(
            int(GRADIENT_START[i] * (1 - progress) + GRADIENT_END[i] * progress)
            for i in range(3)
        )
        pygame.draw.line(screen, color, (0, y), (WINDOW_WIDTH, y))
    
    for i in range(5):
        alpha = 20 + int(10 * math.sin(time_offset * 0.01 + i))
        radius = 100 + int(20 * math.sin(time_offset * 0.008 + i * 2))
        x = (WINDOW_WIDTH // 6) * (i + 1)
        y = WINDOW_HEIGHT // 2 + int(50 * math.sin(time_offset * 0.005 + i))
        
        circle_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(circle_surface, (*LIGHT_BLUE[:3], alpha), (radius, radius), radius)
        screen.blit(circle_surface, (x - radius, y - radius))

def draw_enhanced_title(screen, title, x_pos, y_pos, size=48):
    font = pygame.font.Font(None, size)
    
    shadow_surface = font.render(title, True, DEEP_GRAY)
    shadow_rect = shadow_surface.get_rect(center=(x_pos + 3, y_pos + 3))
    screen.blit(shadow_surface, shadow_rect)
    
    text_surface = font.render(title, True, WHITE)
    text_rect = text_surface.get_rect(center=(x_pos, y_pos))
    screen.blit(text_surface, text_rect)
    
    glow_surface = font.render(title, True, GOLD) 
    glow_rect = glow_surface.get_rect(center=(x_pos, y_pos))
    glow_surf = pygame.Surface((glow_rect.width + 10, glow_rect.height + 10), pygame.SRCALPHA)
    for offset in range(1, 4):
        for dx in [-offset, 0, offset]:
            for dy in [-offset, 0, offset]:
                if dx != 0 or dy != 0:
                    glow_surf.blit(glow_surface, (dx + 5, dy + 5))
    
    glow_surf.set_alpha(30)
    screen.blit(glow_surf, (glow_rect.x - 5, glow_rect.y - 5))

def draw_enhanced_board(screen, board, board_rect, title, clickable=False, is_spectator=False):
    draw_enhanced_title(screen, title, board_rect.centerx, board_rect.top - 40, 32)
    
    shadow_rect = board_rect.copy()
    shadow_rect.x += 5
    shadow_rect.y += 5
    pygame.draw.rect(screen, (0, 0, 0, 100), shadow_rect, border_radius=10)
    
    pygame.draw.rect(screen, NAVY_BLUE, board_rect, border_radius=10)
    pygame.draw.rect(screen, GOLD, board_rect, 3, border_radius=10)
    
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            cell_rect = pygame.Rect(
                board_rect.x + c * CELL_SIZE + 2, 
                board_rect.y + r * CELL_SIZE + 2, 
                CELL_SIZE - 4, 
                CELL_SIZE - 4
            )
            
            cell_value = board[r][c]
            
            if cell_value == 'X':  
                pygame.draw.rect(screen, CRIMSON, cell_rect, border_radius=3)
                center = cell_rect.center
                for i in range(3):
                    radius = 8 - i * 2
                    color_intensity = 255 - i * 50
                    explosion_color = (color_intensity, color_intensity // 4, 0)
                    pygame.draw.circle(screen, explosion_color, center, radius)
            elif cell_value == 'O':  
                pygame.draw.rect(screen, LIGHT_BLUE, cell_rect, border_radius=3)
                center = cell_rect.center
                pygame.draw.circle(screen, WHITE, center, 6, 2)
                pygame.draw.circle(screen, LIGHT_BLUE, center, 4)
            elif is_spectator and cell_value != '.' and cell_value not in ['X', 'O']:
                pygame.draw.rect(screen, DARK_GREEN, cell_rect, border_radius=3)
                pygame.draw.rect(screen, LIGHT_GREEN, cell_rect, 2, border_radius=3)
            else:
                water_color = (70, 130, 180) if (r + c) % 2 == 0 else (65, 125, 175)
                pygame.draw.rect(screen, water_color, cell_rect, border_radius=3)
            
            pygame.draw.rect(screen, SILVER, cell_rect, 1, border_radius=3)
    
    font = pygame.font.Font(None, 20)
    for i in range(BOARD_SIZE):
        row_text = font.render(str(i + 1), True, WHITE)
        screen.blit(row_text, (board_rect.x - 25, board_rect.y + i * CELL_SIZE + CELL_SIZE // 2 - 10))
        
        col_text = font.render(chr(65 + i), True, WHITE)
        screen.blit(col_text, (board_rect.x + i * CELL_SIZE + CELL_SIZE // 2 - 5, board_rect.y - 25))

def draw_enhanced_status_panel(screen, status_message, game_phase, player_name="", opponent_name="", your_turn=False):
    panel_rect = pygame.Rect(50, 50, WINDOW_WIDTH - 100, 80)
    
    panel_surface = pygame.Surface((panel_rect.width, panel_rect.height), pygame.SRCALPHA)
    for y in range(panel_rect.height):
        progress = y / panel_rect.height
        alpha = int(180 * (1 - progress * 0.3))
        color = (*DARK_BLUE, alpha)
        pygame.draw.line(panel_surface, color, (0, y), (panel_rect.width, y))
    
    screen.blit(panel_surface, panel_rect.topleft)
    pygame.draw.rect(screen, GOLD, panel_rect, 3, border_radius=15)
    
    font = pygame.font.Font(None, 36)
    status_surface = font.render(status_message, True, WHITE)
    status_rect = status_surface.get_rect(center=(panel_rect.centerx, panel_rect.centery - 10))
    screen.blit(status_surface, status_rect)
    
    if game_phase == "playing":
        turn_font = pygame.font.Font(None, 24)
        turn_text = f"Your Turn ({player_name})" if your_turn else f"Opponent's Turn ({opponent_name})"
        turn_color = LIGHT_GREEN if your_turn else CRIMSON
        turn_surface = turn_font.render(turn_text, True, turn_color)
        turn_rect = turn_surface.get_rect(center=(panel_rect.centerx, panel_rect.centery + 15))
        screen.blit(turn_surface, turn_rect)


class BattleshipGUI:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Battleship Game (HTTP Client)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.big_font = pygame.font.Font(None, 36)
        self.timer_font = pygame.font.Font(None, 48)
        self.scoreboard_font = pygame.font.Font(None, 22)

        self.client = BattleshipHttpClient()
        self.client.add_message_callback(self.handle_server_message)
        
        self.POLL_GAME_STATE_EVENT = pygame.USEREVENT + 1
        pygame.time.set_timer(self.POLL_GAME_STATE_EVENT, 1000)

        self.game_phase = "main_menu"
        self.disconnected = False
        self.quick_match_last_check = 0
        self.spectate_list_last_check = 0
        self.ongoing_matches = []
        self.reset_game_state()
        self.setup_ui_elements()
        self.load_ship_images()

    def reset_game_state(self):
        self.own_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.opponent_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.spectate_board_p1 = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.spectate_board_p2 = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

        self.your_turn = False
        self.player_number = None
        self.status_message = "Welcome to Battleship!"
        self.player_name = ""
        self.opponent_name = ""
        self.current_turn_player_name = None
        self.room_code = ""
        self.turn_time_remaining = 0
        self.opponent_connected = True
        self.own_sunk_ships = []
        self.opponent_sunk_ships = []
        self.spectate_sunk_ships_p1 = []
        self.spectate_sunk_ships_p2 = []
        self.spectate_p1_name = ""
        self.spectate_p2_name = ""

        self.ships_to_place = [
            {"name": "AircraftCarrier", "length": 5, "placed": False},
            {"name": "Battleship", "length": 4, "placed": False},
            {"name": "Cruiser", "length": 3, "placed": False},
            {"name": "Submarine", "length": 3, "placed": False},
            {"name": "PatrolBoat", "length": 2, "placed": False}
        ]
        self.current_ship_index = 0
        self.ship_orientation = 'H'
        self.placed_ships = []
        self.client.is_spectator = False

    def handle_server_message(self, message):
        msg_type = message.get('type')
        if self.disconnected and msg_type != 'reconnect_success':
            return
            
        if msg_type == 'game_state':
            self.disconnected = False
            self.game_phase = message.get('game_phase', self.game_phase)

            if self.client.is_spectator:
                self.spectate_board_p1 = message.get('player1_board', self.spectate_board_p1)
                self.spectate_board_p2 = message.get('player2_board', self.spectate_board_p2)
                self.spectate_sunk_ships_p1 = message.get('player1_sunk_ships', self.spectate_sunk_ships_p1)
                self.spectate_sunk_ships_p2 = message.get('player2_sunk_ships', self.spectate_sunk_ships_p2)
                self.spectate_p1_name = message.get('player1_name', '')
                self.spectate_p2_name = message.get('player2_name', '')
            else:
                self.own_board = message.get('own_board', self.own_board)
                self.opponent_board = message.get('opponent_board', self.opponent_board)
                self.your_turn = message.get('your_turn', self.your_turn)
                self.player_name = message.get('player_name', self.player_name)
                self.opponent_name = message.get('opponent_name', self.opponent_name)
                self.own_sunk_ships = message.get('own_sunk_ships', self.own_sunk_ships)
                self.opponent_sunk_ships = message.get('opponent_sunk_ships', self.opponent_sunk_ships)
                if message.get('game_phase') != 'placing_ships':
                    self.placed_ships = message.get('placed_ships', self.placed_ships)


            self.status_message = message.get('status_message', self.status_message)
            self.current_turn_player_name = message.get('current_turn_player_name')
            self.turn_time_remaining = message.get('turn_time_remaining', self.turn_time_remaining)
            self.opponent_connected = message.get('opponent_connected', self.opponent_connected)

            if self.client.game_id:
                self.room_code = self.client.game_id
            if self.game_phase == 'waiting_room':
                self.room_code = self.client.game_id

            if self.client.is_spectator and self.game_phase not in ["game_over", "spectating"]:
                self.game_phase = "spectating"
                if message.get('game_phase') == 'playing':
                    self.status_message = f"Spectating: {self.current_turn_player_name}'s Turn"
                elif message.get('game_phase') == 'placing_ships':
                    self.status_message = "Spectating: Players are placing ships."
                elif message.get('game_phase') == 'game_over':
                    self.status_message = f"Spectating: Game Over! {message.get('winner', 'Unknown')} wins!"


        elif msg_type == 'room_join_status' and not message['success']:
            self.status_message = message['message']
            self.game_phase = 'join_game' 
            
        elif msg_type == 'ships_placed' and message['success']:
            self.status_message = "Ships placed! Waiting for opponent..."
        
        elif msg_type == 'error':
            self.status_message = message.get('message', 'An unknown error occurred.')

        elif msg_type == 'disconnect_error':
            self.disconnected = True
            self.status_message = "Disconnected from server. Attempting to reconnect..."

        elif msg_type == 'reconnect_success':
            self.disconnected = False
            self.status_message = "Reconnected successfully!"

        elif msg_type == 'quick_match_waiting':
            self.game_phase = "quick_match_waiting"
            self.status_message = "Looking for opponent..."

        elif msg_type == 'quick_match_found':
            self.status_message = f"Match found! Playing against {message.get('opponent_name', 'opponent')}"
            self.game_phase = "placing_ships"

        elif msg_type == 'quick_match_cancelled':
            self.status_message = "Quick match cancelled."
            self.game_phase = "main_menu"
            
        elif msg_type == 'ongoing_matches':
            self.ongoing_matches = message.get('matches', [])
            self.status_message = "Select a quick match to spectate."

            self.spectate_list_buttons = []
            y_start = WINDOW_HEIGHT // 2 - 120
            x_start = WINDOW_WIDTH // 2 - 250
            for i, match in enumerate(self.ongoing_matches):
                spectate_button = EnhancedButton(
                    x_start + 300, y_start + i * 60 - 10, 100, 40, "Spectate",
                    DARK_BLUE, LIGHT_BLUE,
                    action=lambda game_id=match['game_id']: self.client.spectate_game(game_id)
                )
                self.spectate_list_buttons.append(spectate_button)

        elif msg_type == 'spectate_success':
            self.status_message = "Successfully joined as spectator."
            self.game_phase = "spectating"

    def run(self):
        running = True
        while running:
            mouse_pos = pygame.mouse.get_pos()

            if self.game_phase == "host_game":
                self.host_game_inputs['name_input'].update()
            elif self.game_phase == "join_game":
                self.join_game_inputs['name_input'].update()
                self.join_game_inputs['code_input'].update()
            elif self.game_phase == "quick_match":
                self.quick_match_inputs['name_input'].update()

            if self.client.game_id and time.time() - self.client.last_successful_poll > 6:
                self.disconnected = True
                self.status_message = "Disconnected. Click to reconnect."

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                if self.disconnected:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                         self.client.reconnect()
                    continue

                if event.type == self.POLL_GAME_STATE_EVENT:
                    if self.client.game_id and self.game_phase not in ["main_menu", "host_game", "join_game", "quick_match", "spectate_list"]:
                        self.client.get_game_state()
                    elif self.game_phase == "quick_match_waiting":
                        current_time = time.time()
                        if current_time - self.quick_match_last_check >= 2:
                            self.quick_match_last_check = current_time
                            self.client.check_quick_match_status()
                    elif self.game_phase == "spectate_list":
                        current_time = time.time()
                        if current_time - self.spectate_list_last_check >= 3:
                            self.spectate_list_last_check = current_time
                            self.client.get_ongoing_quick_matches()

                if self.game_phase == "main_menu":
                    for button in self.main_menu_buttons: button.handle_event(event)
                elif self.game_phase == "host_game":
                    self.host_game_inputs['name_input'].handle_event(event)
                    self.host_game_inputs['host_button'].handle_event(event)
                    self.host_game_inputs['back_button'].handle_event(event)
                elif self.game_phase == "join_game":
                    self.join_game_inputs['name_input'].handle_event(event)
                    self.join_game_inputs['code_input'].handle_event(event)
                    self.join_game_inputs['join_button'].handle_event(event)
                    self.join_game_inputs['back_button'].handle_event(event)
                elif self.game_phase == "quick_match":
                    self.quick_match_inputs['name_input'].handle_event(event)
                    self.quick_match_inputs['quick_match_button'].handle_event(event)
                    self.quick_match_inputs['back_button'].handle_event(event)
                elif self.game_phase == "quick_match_waiting":
                    self.quick_match_waiting_inputs['cancel_button'].handle_event(event)
                    self.quick_match_waiting_inputs['back_button'].handle_event(event)
                elif self.game_phase == "placing_ships":
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                        self.ship_orientation = 'V' if self.ship_orientation == 'H' else 'H'
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.place_ship(mouse_pos)
                elif self.game_phase == "playing":
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.attack_opponent(mouse_pos)
                elif self.game_phase == "game_over":
                     self.main_menu_button.handle_event(event)
                elif self.game_phase == "spectate_list":
                    for button in self.spectate_list_buttons:
                        if button.handle_event(event):
                            break
                    self.spectate_list_back_button.handle_event(event)
                elif self.game_phase == "spectating":
                    self.main_menu_button.handle_event(event)

            draw_animated_background(self.screen, pygame.time.get_ticks())
            self.draw_status()

            if self.disconnected:
                 self.draw_disconnected_overlay()
            elif self.game_phase == "main_menu":
                draw_enhanced_title(self.screen, "Battleship Game", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 200, 64)
                for button in self.main_menu_buttons: button.draw(self.screen)
            elif self.game_phase == "host_game":
                draw_enhanced_title(self.screen, "Host Game", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 170)
                name_label = self.font.render("Enter your name:", True, WHITE) 
                self.screen.blit(name_label, (WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 80))
                self.host_game_inputs['name_input'].draw(self.screen)
                self.host_game_inputs['host_button'].draw(self.screen)
                self.host_game_inputs['back_button'].draw(self.screen)
            elif self.game_phase == "join_game":
                draw_enhanced_title(self.screen, "Join/Reconnect Game", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 190)
                name_label = self.font.render("Enter your name:", True, WHITE) 
                self.screen.blit(name_label, (WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 130))
                code_label = self.font.render("Enter room code:", True, WHITE) 
                self.screen.blit(code_label, (WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 70))
                self.join_game_inputs['name_input'].draw(self.screen)
                self.join_game_inputs['code_input'].draw(self.screen)
                self.join_game_inputs['join_button'].draw(self.screen)
                self.join_game_inputs['back_button'].draw(self.screen)
            elif self.game_phase == "quick_match":
                draw_enhanced_title(self.screen, "Quick Match", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 170)
                name_label = self.font.render("Enter your name:", True, WHITE) 
                self.screen.blit(name_label, (WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 80))
                self.quick_match_inputs['name_input'].draw(self.screen)
                self.quick_match_inputs['quick_match_button'].draw(self.screen)
                self.quick_match_inputs['back_button'].draw(self.screen)
            elif self.game_phase == "quick_match_waiting":
                draw_enhanced_title(self.screen, "Finding Match...", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 130)
                wait_text = self.font.render("Please wait while we find you an opponent", True, WHITE)
                self.screen.blit(wait_text, (WINDOW_WIDTH // 2 - wait_text.get_width() // 2, WINDOW_HEIGHT // 2 - 40))
                dots = [".", "..", "...", "....", "....."]
                dot_index = (pygame.time.get_ticks() // 300) % len(dots)
                dots_text = self.font.render(dots[dot_index], True, WHITE)
                self.screen.blit(dots_text, (WINDOW_WIDTH // 2 - dots_text.get_width() // 2, WINDOW_HEIGHT // 2 - 10))
                self.quick_match_waiting_inputs['cancel_button'].draw(self.screen)
                self.quick_match_waiting_inputs['back_button'].draw(self.screen)
            elif self.game_phase == "waiting_room":
                draw_enhanced_title(self.screen, "Waiting Room", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 100)
                if self.room_code:
                    code_text = self.big_font.render(f"Room Code: {self.room_code}", True, WHITE) 
                    self.screen.blit(code_text, (WINDOW_WIDTH // 2 - code_text.get_width() // 2, WINDOW_HEIGHT // 2 - 50))
                wait_text = self.big_font.render("Waiting for opponent...", True, WHITE) 
                self.screen.blit(wait_text, (WINDOW_WIDTH // 2 - wait_text.get_width() // 2, WINDOW_HEIGHT // 2 + 10))
            elif self.game_phase == "placing_ships":
                draw_enhanced_board(self.screen, self.own_board, self.own_board_rect, f"{self.player_name}'s Board")
                self.draw_ship_sprites()
                self.draw_ship_list(self.own_board_rect.right + 80, self.own_board_rect.top + 20)
                self.draw_ship_placement_preview(mouse_pos)
            elif self.game_phase == "playing":
                own_board_title = f"{self.player_name}'s Board"
                opponent_board_title = f"{self.opponent_name}'s Board"
                if self.client.player_number == 1:
                    own_board_title = f"{self.player_name}'s Board (Player 1)"
                    opponent_board_title = f"{self.opponent_name}'s Board (Player 2)"
                elif self.client.player_number == 2:
                    own_board_title = f"{self.player_name}'s Board (Player 2)"
                    opponent_board_title = f"{self.opponent_name}'s Board (Player 1)"
                draw_enhanced_board(self.screen, self.own_board, self.own_board_rect, own_board_title)
                self.draw_ship_sprites()
                self.draw_scoreboard(self.own_board_rect, self.opponent_sunk_ships)
                draw_enhanced_board(self.screen, self.opponent_board, self.opponent_board_rect, opponent_board_title, True)
                self.draw_scoreboard(self.opponent_board_rect, self.own_sunk_ships)
                self.draw_timer_and_code(y_offset_timer=self.own_board_rect.top - 60, y_offset_code=self.own_board_rect.top - 25)
                if not self.opponent_connected:
                    opp_disc_text = self.font.render("Opponent disconnected", True, CRIMSON)
                    self.screen.blit(opp_disc_text, (self.opponent_board_rect.centerx - opp_disc_text.get_width() // 2, self.opponent_board_rect.bottom + 120))
            elif self.game_phase == "game_over":
                draw_enhanced_title(self.screen, f"Game Over! {self.status_message.split('! ')[-1]}", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 100)
                self.main_menu_button.draw(self.screen)
            elif self.game_phase == "spectate_list":
                draw_enhanced_title(self.screen, "Ongoing Quick Matches", WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 200)
                self.draw_ongoing_matches()
                self.spectate_list_back_button.draw(self.screen)
            elif self.game_phase == "spectating":
                draw_enhanced_board(self.screen, self.spectate_board_p1, self.own_board_rect, f"{self.spectate_p1_name}'s Board (Player 1)", is_spectator=True)
                self.draw_scoreboard(self.own_board_rect, self.spectate_sunk_ships_p2)
                
                draw_enhanced_board(self.screen, self.spectate_board_p2, self.opponent_board_rect, f"{self.spectate_p2_name}'s Board (Player 2)", is_spectator=True)
                self.draw_scoreboard(self.opponent_board_rect, self.spectate_sunk_ships_p1)

                self.draw_timer_and_code(y_offset_timer=self.own_board_rect.top - 60, y_offset_code=self.own_board_rect.top - 25)
                self.main_menu_button.draw(self.screen)
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()
        sys.exit()


    def load_ship_images(self):
        self.ship_images = {}
        ship_asset_map = {"AircraftCarrier": "assets/AircraftCarrier.png", "Battleship": "assets/BattleShip.png", "Cruiser": "assets/Cruiser.png", "Submarine": "assets/Submarine.png", "PatrolBoat": "assets/PatrolBoat.png"}
        for ship_data in self.ships_to_place:
            try:
                self.ship_images[ship_data['name']] = pygame.image.load(ship_asset_map[ship_data['name']]).convert_alpha()
            except pygame.error as e:
                print(f"ERROR: Could not load image for {ship_data['name']}: {e}")
                self.ship_images[ship_data['name']] = None

    def setup_ui_elements(self):
        btn_width, btn_height, spacing = 200, 60, 20
        start_y = WINDOW_HEIGHT // 2 - (btn_height * 2 + spacing * 1.5)
        self.main_menu_buttons = [
            EnhancedButton(WINDOW_WIDTH // 2 - btn_width // 2, start_y, btn_width, btn_height, "Host Game", BLUE, LIGHT_BLUE, self.go_to_host_game),
            EnhancedButton(WINDOW_WIDTH // 2 - btn_width // 2, start_y + btn_height + spacing, btn_width, btn_height, "Quick Match", DARK_GREEN, LIGHT_GREEN, self.go_to_quick_match),
            EnhancedButton(WINDOW_WIDTH // 2 - btn_width // 2, start_y + (btn_height + spacing) * 2, btn_width, btn_height, "Join/Reconnect", BLUE, LIGHT_BLUE, self.go_to_join_game),
            EnhancedButton(WINDOW_WIDTH // 2 - btn_width // 2, start_y + (btn_height + spacing) * 3, btn_width, btn_height, "Spectate Match", DARK_BLUE, LIGHT_BLUE, self.go_to_spectate_list)
        ]
        self.host_game_inputs = {
            'name_input': EnhancedInputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 50, 300, 50, '', "Enter your name"), 
            'host_button': EnhancedButton(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Host", DARK_GREEN, LIGHT_GREEN, self.host_private_game), 
            'back_button': EnhancedButton(50, 50, 100, 40, "Back", DEEP_GRAY, SILVER, self.go_to_main_menu) 
        }
        self.join_game_inputs = {
            'name_input': EnhancedInputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 80, 300, 50, '', "Enter your name"), 
            'code_input': EnhancedInputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 20, 300, 50, '', "Enter room code"), 
            'join_button': EnhancedButton(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Join/Reconnect", DARK_GREEN, LIGHT_GREEN, self.join_private_game), 
            'back_button': EnhancedButton(50, 50, 100, 40, "Back", DEEP_GRAY, SILVER, self.go_to_main_menu) 
        }
        self.quick_match_inputs = {
            'name_input': EnhancedInputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 50, 300, 50, '', "Enter your name"), 
            'quick_match_button': EnhancedButton(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Find Match", DARK_GREEN, LIGHT_GREEN, self.start_quick_match), 
            'back_button': EnhancedButton(50, 50, 100, 40, "Back", DEEP_GRAY, SILVER, self.go_to_main_menu) 
        }
        self.quick_match_waiting_inputs = {
            'cancel_button': EnhancedButton(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 100, 200, 50, "Cancel", CRIMSON, RED, self.cancel_quick_match_search), 
            'back_button': EnhancedButton(50, 50, 100, 40, "Back", DEEP_GRAY, SILVER, self.cancel_quick_match_search) 
        }
        self.own_board_rect = pygame.Rect(BOARD_MARGIN, BOARD_MARGIN + 150, BOARD_SIZE * CELL_SIZE + 4, BOARD_SIZE * CELL_SIZE + 4)
        self.opponent_board_rect = pygame.Rect(WINDOW_WIDTH - BOARD_MARGIN - BOARD_SIZE * CELL_SIZE - 4, BOARD_MARGIN + 150, BOARD_SIZE * CELL_SIZE + 4, BOARD_SIZE * CELL_SIZE + 4)
        self.main_menu_button = EnhancedButton(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 150, 200, 50, "Main Menu", DARK_BLUE, LIGHT_BLUE, self.go_to_main_menu) 

        self.spectate_list_buttons = []
        self.spectate_list_back_button = EnhancedButton(50, 50, 100, 40, "Back", DEEP_GRAY, SILVER, self.go_to_main_menu) 


    def go_to_main_menu(self): self.game_phase = "main_menu"; self.reset_game_state(); self.client = BattleshipHttpClient(); self.client.add_message_callback(self.handle_server_message)
    def go_to_host_game(self): self.game_phase = "host_game"; self.status_message = "Enter your name to host a game."
    def go_to_join_game(self): self.game_phase = "join_game"; self.status_message = "Enter name and code to join or reconnect."
    def go_to_quick_match(self): 
        self.game_phase = "quick_match"
        self.status_message = "Enter your name for quick match."
        self.client.game_id = None
        self.client.player_number = None
        self.reset_game_state()

    def go_to_spectate_list(self):
        self.game_phase = "spectate_list"
        self.status_message = "Loading ongoing matches..."
        self.client.is_spectator = True
        self.spectate_list_last_check = time.time()
        self.client.get_ongoing_quick_matches()
        
    def start_quick_match(self):
        player_name = self.quick_match_inputs['name_input'].get_text().strip()
        if player_name:
            self.client.game_id = None
            self.client.player_number = None
            self.reset_game_state()
            self.quick_match_last_check = time.time()
            
            self.client.quick_match(player_name)
            self.game_phase = "quick_match_waiting"
            self.status_message = "Looking for opponent..."
        else:
            self.status_message = "Please enter your name."

    def cancel_quick_match_search(self):
        self.client.cancel_quick_match()
        self.go_to_main_menu()

    def host_private_game(self):
        player_name = self.host_game_inputs['name_input'].get_text().strip()
        if player_name: self.client.host_game(player_name)
        else: self.status_message = "Please enter your name."
    
    def join_private_game(self):
        player_name = self.join_game_inputs['name_input'].get_text().strip()
        room_code = self.join_game_inputs['code_input'].get_text().strip()
        if player_name and room_code: self.client.join_private_game(player_name, room_code)
        else: self.status_message = "Please enter your name and the room code."
        
    def attack_opponent(self, mouse_pos):
        if not self.your_turn or self.game_phase != "playing": return
        if self.opponent_board_rect.collidepoint(mouse_pos):
            col = (mouse_pos[0] - self.opponent_board_rect.x) // CELL_SIZE
            row = (mouse_pos[1] - self.opponent_board_rect.y) // CELL_SIZE
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE and self.opponent_board[row][col] == '.':
                self.client.attack(row, col)

    def place_ship(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place): return
        ship = self.ships_to_place[self.current_ship_index]
        if self.own_board_rect.collidepoint(mouse_pos):
            col = (mouse_pos[0] - self.own_board_rect.x) // CELL_SIZE
            row = (mouse_pos[1] - self.own_board_rect.y) // CELL_SIZE
            can_place, cells_to_place = self.check_placement(ship, row, col)
            if can_place:
                for r, c in cells_to_place: self.own_board[r][c] = ship['name'][0]
                ship['placed'] = True
                self.placed_ships.append({'name': ship['name'], 'start_row': row, 'start_col': col, 'orientation': self.ship_orientation})
                self.current_ship_index += 1
                if self.current_ship_index >= len(self.ships_to_place):
                    self.client.place_ships(self.placed_ships)
    
    def check_placement(self, ship, row, col):
        cells = []
        if self.ship_orientation == 'H':
            if col + ship['length'] > BOARD_SIZE: return False, []
            for c in range(col, col + ship['length']):
                if self.own_board[row][c] != '.': return False, []
                cells.append((row, c))
        else: 
            if row + ship['length'] > BOARD_SIZE: return False, []
            for r in range(row, row + ship['length']):
                if self.own_board[r][col] != '.': return False, []
                cells.append((r, col))
        return True, cells

    def draw_status(self):
        draw_enhanced_status_panel(self.screen, self.status_message, self.game_phase, 
                                   self.player_name, self.opponent_name, self.your_turn)

    def draw_timer_and_code(self, y_offset_timer, y_offset_code):
        if self.turn_time_remaining is not None:
            time_text = f"{int(self.turn_time_remaining)}"
            color = WHITE if self.turn_time_remaining > 10 else CRIMSON 
            timer_surface = self.timer_font.render(time_text, True, color)
            x = WINDOW_WIDTH // 2
            y = y_offset_timer
            bg_rect = timer_surface.get_rect(center=(x, y))
            pygame.draw.rect(self.screen, NAVY_BLUE, bg_rect.inflate(10, 10), border_radius=5) 
            pygame.draw.rect(self.screen, GOLD, bg_rect.inflate(10, 10), 2, border_radius=5) 
            self.screen.blit(timer_surface, timer_surface.get_rect(center=(x, y)))

        if self.room_code:
            code_surface = self.font.render(f"Room Code: {self.room_code}", True, WHITE) 
            code_rect = code_surface.get_rect(center=(WINDOW_WIDTH // 2, y_offset_code))
            self.screen.blit(code_surface, code_rect)

    def draw_scoreboard(self, board_rect, sunk_ships):
        y_start = board_rect.bottom + 20
        title_surf = self.scoreboard_font.render("Sunk Ships:", True, WHITE) 
        self.screen.blit(title_surf, (board_rect.left, y_start))
        
        if not sunk_ships:
            none_surf = self.scoreboard_font.render("None", True, SILVER) 
            self.screen.blit(none_surf, (board_rect.left + 100, y_start))

        for i, ship_name in enumerate(sunk_ships):
            ship_surf = self.scoreboard_font.render(ship_name, True, CRIMSON) 
            self.screen.blit(ship_surf, (board_rect.left, y_start + 20 + (i * 20)))

    def draw_disconnected_overlay(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180)) 
        self.screen.blit(overlay, (0, 0))
        
        text = self.big_font.render("Disconnected", True, CRIMSON) 
        self.screen.blit(text, text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 40)))

        sub_text = self.font.render("Click anywhere to try reconnecting...", True, SOFT_WHITE) 
        self.screen.blit(sub_text, sub_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 10)))

    def draw_ship_sprites(self):
        for ship in self.placed_ships:
            original_image = self.ship_images.get(ship['name'])
            if original_image:
                ship_details = next((s for s in self.ships_to_place if s['name'] == ship['name']), None)
                if not ship_details: continue
                length = ship_details['length']

                if ship['orientation'] == 'H':
                    scaled_image = pygame.transform.scale(original_image, (length * CELL_SIZE, CELL_SIZE))
                else: 
                    rotated_image = pygame.transform.rotate(original_image, 90)
                    scaled_image = pygame.transform.scale(rotated_image, (CELL_SIZE, length * CELL_SIZE))
                self.screen.blit(scaled_image, (self.own_board_rect.x + ship['start_col'] * CELL_SIZE + 2, self.own_board_rect.y + ship['start_row'] * CELL_SIZE + 2))

    def draw_ship_placement_preview(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place): return
        ship = self.ships_to_place[self.current_ship_index]
        if self.own_board_rect.collidepoint(mouse_pos):
            col = (mouse_pos[0] - self.own_board_rect.x) // CELL_SIZE
            row = (mouse_pos[1] - self.own_board_rect.y) // CELL_SIZE
            can_place, cells = self.check_placement(ship, row, col)
            color = LIGHT_GREEN if can_place else CRIMSON 
            for r, c in cells:
                preview_rect = pygame.Rect(self.own_board_rect.x + c * CELL_SIZE + 2, self.own_board_rect.y + r * CELL_SIZE + 2, CELL_SIZE - 4, CELL_SIZE - 4)
                
                s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                s.fill((color[0], color[1], color[2], 128))
                pygame.draw.rect(s, color, s.get_rect(), 2, border_radius=3) 
                self.screen.blit(s, preview_rect.topleft)


    def draw_ship_list(self, x_offset, y_offset):
        title_surf = self.big_font.render("Place Your Fleet (R to rotate)", True, WHITE)
        self.screen.blit(title_surf, (x_offset, y_offset))
        y_offset += 50
        for i, ship in enumerate(self.ships_to_place):
            color = LIGHT_GREEN if ship['placed'] else (LIGHT_BLUE if i == self.current_ship_index else SOFT_WHITE)
            text = f"{ship['name']} ({ship['length']})"
            if i == self.current_ship_index and not ship['placed']:
                 text += f" - Placing ({self.ship_orientation})"
            self.screen.blit(self.font.render(text, True, color), (x_offset, y_offset + i * 30))

    def draw_ongoing_matches(self):
        y_start = WINDOW_HEIGHT // 2 - 120
        x_start = WINDOW_WIDTH // 2 - 250
        
        if not self.ongoing_matches:
            no_matches_text = self.font.render("No ongoing quick matches.", True, WHITE) 
            self.screen.blit(no_matches_text, (x_start + 50, y_start))
        else:
            for i, match in enumerate(self.ongoing_matches):
                match_text = f"{match['player1_name']} vs {match['player2_name']}"
                text_surface = self.font.render(match_text, True, SOFT_WHITE) 
                self.screen.blit(text_surface, (x_start, y_start + i * 60))

            for button in self.spectate_list_buttons:
                button.draw(self.screen)

if __name__ == '__main__':
    game = BattleshipGUI()
    game.run()