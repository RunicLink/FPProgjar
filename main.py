# main.py (HTTP version)
import pygame
import sys
import json
import time
import socket

# --- NEW HTTP CLIENT ---
class BattleshipHttpClient:
    """A client to interact with the Battleship HTTP server."""
    def __init__(self, host='localhost', port=8889):
        self.host = host
        self.port = port
        self.game_id = None
        self.player_number = None
        self.player_name = None
        self.message_callbacks = []
        self.last_successful_poll = time.time()

    def add_message_callback(self, callback):
        """Adds a callback function to be invoked with server responses."""
        self.message_callbacks.append(callback)

    def _send_request(self, method, path, payload=None):
        """Constructs and sends an HTTP request, then parses the response."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.connect((self.host, self.port))
                body = json.dumps(payload) if payload else ''
                request = (
                    f"{method} {path} HTTP/1.0\r\n"
                    f"Host: {self.host}:{self.port}\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n\r\n"
                    f"{body}"
                )
                sock.sendall(request.encode('utf-8'))

                response_data = b''
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                
                if not response_data:
                    self._notify_listeners({'type': 'error', 'message': 'Empty response from server'})
                    return None
                
                header_part, body_part = response_data.split(b'\r\n\r\n', 1)
                self.last_successful_poll = time.time()
                return json.loads(body_part.decode('utf-8'))
            except Exception as e:
                print(f"HTTP request to {path} failed: {e}")
                self._notify_listeners({'type': 'disconnect_error', 'message': f'Connection failed: {e}'})
                return None

    def host_game(self, player_name):
        self.player_name = player_name
        response = self._send_request('POST', '/api/host', {'player_name': player_name})
        if response and 'game_id' in response:
            self.game_id = response['game_id']
            self.player_number = response['player_number']
            self.get_game_state()
        else:
            self._notify_listeners({'type': 'error', 'message': 'Could not host game.'})

    def join_private_game(self, player_name, room_code):
        self.player_name = player_name
        response = self._send_request('POST', '/api/join', {'player_name': player_name, 'game_id': room_code})
        if response and 'player_number' in response:
            self.game_id = room_code
            self.player_number = response['player_number']
            self.get_game_state()
        elif response:
            error_msg = response.get('error', 'Could not join game.')
            self._notify_listeners({'type': 'room_join_status', 'success': False, 'message': error_msg})

    def reconnect(self):
        if not self.player_name or not self.game_id:
            return
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
        if not self.game_id or self.player_number is None:
            return
        path = f"/api/gamestate?game_id={self.game_id}&player_number={self.player_number}"
        response = self._send_request('GET', path)
        if response:
            self._notify_listeners(response)
    
    def _notify_listeners(self, message):
        for callback in self.message_callbacks:
            callback(message)

# --- Pygame GUI (Adapted for HTTP Polling) ---
pygame.init()

# Constants and Colors
WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 800
BOARD_SIZE, CELL_SIZE, BOARD_MARGIN = 10, 40, 50
WHITE, BLACK, BLUE, RED, GREEN, GRAY, LIGHT_GRAY = (255, 255, 255), (0, 0, 0), (0, 100, 200), (200, 0, 0), (0, 200, 0), (128, 128, 128), (200, 200, 200)
ORANGE = (255, 165, 0)

# (InputBox and Button classes are unchanged from your original file)
class InputBox:
    def __init__(self, x, y, w, h, text=''):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = BLACK
        self.text = text
        self.font = pygame.font.Font(None, 32)
        self.active = False
        self.txt_surface = self.font.render(text, True, self.color)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = not self.active
            else:
                self.active = False
            self.color = BLUE if self.active else BLACK
        if event.type == pygame.KEYDOWN:
            if self.active:
                if event.key == pygame.K_RETURN:
                    self.active = False
                    self.color = BLACK
                    return True
                elif event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                else:
                    self.text += event.unicode
                self.txt_surface = self.font.render(self.text, True, self.color)
        return False

    def draw(self, screen):
        screen.blit(self.txt_surface, (self.rect.x + 5, self.rect.y + 5))
        pygame.draw.rect(screen, self.color, self.rect, 2)

    def get_text(self):
        return self.text

class Button:
    def __init__(self, x, y, w, h, text, color, hover_color, action=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.current_color = color
        self.action = action
        self.font = pygame.font.Font(None, 36)
        self.text_surface = self.font.render(text, True, WHITE)
        self.text_rect = self.text_surface.get_rect(center=self.rect.center)

    def draw(self, screen):
        pygame.draw.rect(screen, self.current_color, self.rect)
        screen.blit(self.text_surface, self.text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            if self.rect.collidepoint(event.pos):
                self.current_color = self.hover_color
            else:
                self.current_color = self.color
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if self.action:
                    self.action()
                    return True
        return False

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
        self.reset_game_state()
        self.setup_ui_elements()
        self.load_ship_images()

    def reset_game_state(self):
        self.own_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.opponent_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
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

    def handle_server_message(self, message):
        msg_type = message.get('type')
        if self.disconnected and msg_type != 'reconnect_success':
            return
            
        if msg_type == 'game_state':
            self.disconnected = False
            self.game_phase = message.get('game_phase', self.game_phase)
            self.own_board = message.get('own_board', self.own_board)
            self.opponent_board = message.get('opponent_board', self.opponent_board)
            self.your_turn = message.get('your_turn', self.your_turn)
            self.status_message = message.get('status_message', self.status_message)
            self.player_name = message.get('player_name', self.player_name)
            self.opponent_name = message.get('opponent_name', self.opponent_name)
            self.current_turn_player_name = message.get('current_turn_player_name')
            self.turn_time_remaining = message.get('turn_time_remaining', self.turn_time_remaining)
            self.opponent_connected = message.get('opponent_connected', self.opponent_connected)
            self.own_sunk_ships = message.get('own_sunk_ships', self.own_sunk_ships)
            self.opponent_sunk_ships = message.get('opponent_sunk_ships', self.opponent_sunk_ships)

            if self.client.game_id:
                self.room_code = self.client.game_id
            if self.game_phase == 'waiting_room':
                self.room_code = self.client.game_id

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


    def run(self):
        running = True
        while running:
            mouse_pos = pygame.mouse.get_pos()
            
            if self.client.game_id and time.time() - self.client.last_successful_poll > 10:
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
                    if self.client.game_id and self.game_phase not in ["main_menu", "host_game", "join_game"]:
                        self.client.get_game_state()

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

            self.screen.fill(LIGHT_GRAY)
            self.draw_status()

            if self.disconnected:
                 self.draw_disconnected_overlay()
            elif self.game_phase == "main_menu":
                for button in self.main_menu_buttons: button.draw(self.screen)
            elif self.game_phase == "host_game":
                self.host_game_inputs['name_input'].draw(self.screen)
                self.host_game_inputs['host_button'].draw(self.screen)
                self.host_game_inputs['back_button'].draw(self.screen)
            elif self.game_phase == "join_game":
                self.join_game_inputs['name_input'].draw(self.screen)
                self.join_game_inputs['code_input'].draw(self.screen)
                self.join_game_inputs['join_button'].draw(self.screen)
                self.join_game_inputs['back_button'].draw(self.screen)
            elif self.game_phase == "waiting_room":
                if self.room_code:
                    code_text = self.big_font.render(f"Room Code: {self.room_code}", True, BLACK)
                    self.screen.blit(code_text, (WINDOW_WIDTH // 2 - code_text.get_width() // 2, WINDOW_HEIGHT // 2 - 50))
                wait_text = self.big_font.render("Waiting for opponent...", True, BLACK)
                self.screen.blit(wait_text, (WINDOW_WIDTH // 2 - wait_text.get_width() // 2, WINDOW_HEIGHT // 2 + 10))
            elif self.game_phase == "placing_ships":
                self.draw_board(self.own_board, self.own_board_rect, f"{self.player_name}'s Board")
                self.draw_ship_sprites()
                self.draw_ship_list()
                self.draw_ship_placement_preview(mouse_pos)
            elif self.game_phase == "playing":
                self.draw_board(self.own_board, self.own_board_rect, f"{self.player_name}'s Board")
                self.draw_ship_sprites()
                self.draw_scoreboard(self.own_board_rect, self.opponent_sunk_ships)
                
                self.draw_board(self.opponent_board, self.opponent_board_rect, f"{self.opponent_name}'s Board", True)
                self.draw_scoreboard(self.opponent_board_rect, self.own_sunk_ships)
                
                self.draw_timer_and_code()
                if not self.opponent_connected:
                    opp_disc_text = self.font.render("Opponent disconnected", True, RED)
                    self.screen.blit(opp_disc_text, (self.opponent_board_rect.centerx - opp_disc_text.get_width() // 2, self.opponent_board_rect.bottom + 120))
            elif self.game_phase == "game_over":
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
        start_y = WINDOW_HEIGHT // 2 - (btn_height * 1.5 + spacing)
        self.main_menu_buttons = [
            Button(WINDOW_WIDTH // 2 - btn_width // 2, start_y, btn_width, btn_height, "Host Game", BLUE, ORANGE, self.go_to_host_game),
            Button(WINDOW_WIDTH // 2 - btn_width // 2, start_y + btn_height + spacing, btn_width, btn_height, "Join/Reconnect", BLUE, ORANGE, self.go_to_join_game)
        ]
        self.host_game_inputs = {
            'name_input': InputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 50, 300, 40, ''),
            'host_button': Button(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Host", GREEN, ORANGE, self.host_private_game),
            'back_button': Button(50, 50, 100, 40, "Back", GRAY, ORANGE, self.go_to_main_menu)
        }
        self.join_game_inputs = {
            'name_input': InputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 100, 300, 40, ''),
            'code_input': InputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 40, 300, 40, ''),
            'join_button': Button(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Join/Reconnect", GREEN, ORANGE, self.join_private_game),
            'back_button': Button(50, 50, 100, 40, "Back", GRAY, ORANGE, self.go_to_main_menu)
        }
        self.own_board_rect = pygame.Rect(BOARD_MARGIN, BOARD_MARGIN + 100, BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)
        self.opponent_board_rect = pygame.Rect(WINDOW_WIDTH - BOARD_MARGIN - BOARD_SIZE * CELL_SIZE, BOARD_MARGIN + 100, BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)
        self.main_menu_button = Button(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Main Menu", BLUE, ORANGE, self.go_to_main_menu)


    def go_to_main_menu(self): self.game_phase = "main_menu"; self.reset_game_state(); self.client = BattleshipHttpClient(); self.client.add_message_callback(self.handle_server_message)
    def go_to_host_game(self): self.game_phase = "host_game"; self.status_message = "Enter your name to host a game."
    def go_to_join_game(self): self.game_phase = "join_game"; self.status_message = "Enter name and code to join or reconnect."

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
        else: # 'V'
            if row + ship['length'] > BOARD_SIZE: return False, []
            for r in range(row, row + ship['length']):
                if self.own_board[r][col] != '.': return False, []
                cells.append((r, col))
        return True, cells

    def draw_status(self):
        status_surface = self.big_font.render(self.status_message, True, BLACK)
        self.screen.blit(status_surface, (WINDOW_WIDTH / 2 - status_surface.get_width() / 2, 10))
        if self.game_phase == "playing":
            turn_text = f"Your Turn ({self.player_name})" if self.your_turn else f"Opponent's Turn ({self.opponent_name})"
            turn_color = GREEN if self.your_turn else RED
            turn_surface = self.font.render(turn_text, True, turn_color)
            self.screen.blit(turn_surface, (WINDOW_WIDTH / 2 - turn_surface.get_width() / 2, 50))

    def draw_timer_and_code(self):
        # Timer
        if self.turn_time_remaining is not None:
            time_text = f"{int(self.turn_time_remaining)}"
            color = WHITE if self.turn_time_remaining > 10 else RED
            timer_surface = self.timer_font.render(time_text, True, color)
            x = WINDOW_WIDTH // 2
            y = self.own_board_rect.top - 60
            bg_rect = timer_surface.get_rect(center=(x, y))
            pygame.draw.rect(self.screen, BLACK, bg_rect.inflate(10, 10))
            self.screen.blit(timer_surface, timer_surface.get_rect(center=(x, y)))

        # Room Code
        if self.room_code:
            code_surface = self.font.render(f"Room Code: {self.room_code}", True, BLACK)
            code_rect = code_surface.get_rect(center=(WINDOW_WIDTH // 2, self.own_board_rect.top - 25))
            self.screen.blit(code_surface, code_rect)

    def draw_scoreboard(self, board_rect, sunk_ships):
        y_start = board_rect.bottom + 20
        title_surf = self.scoreboard_font.render("Sunk Ships:", True, BLACK)
        self.screen.blit(title_surf, (board_rect.left, y_start))
        
        if not sunk_ships:
            none_surf = self.scoreboard_font.render("None", True, GRAY)
            self.screen.blit(none_surf, (board_rect.left + 80, y_start))

        for i, ship_name in enumerate(sunk_ships):
            ship_surf = self.scoreboard_font.render(ship_name, True, RED)
            self.screen.blit(ship_surf, (board_rect.left, y_start + 20 + (i * 20)))

    def draw_disconnected_overlay(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180)) 
        self.screen.blit(overlay, (0, 0))
        
        text = self.big_font.render("Disconnected", True, RED)
        self.screen.blit(text, text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 40)))

        sub_text = self.font.render("Click anywhere to try reconnecting...", True, WHITE)
        self.screen.blit(sub_text, sub_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 10)))

    def draw_board(self, board, board_rect, title, clickable=False):
        title_surface = self.big_font.render(title, True, BLACK)
        self.screen.blit(title_surface, (board_rect.centerx - title_surface.get_width() / 2, board_rect.top - 40))
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cell_rect = pygame.Rect(board_rect.x + c * CELL_SIZE, board_rect.y + r * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                pygame.draw.rect(self.screen, WHITE, cell_rect)
                cell_value = board[r][c]
                if cell_value == 'X':
                    pygame.draw.rect(self.screen, RED, cell_rect)
                elif cell_value == 'O':
                    pygame.draw.rect(self.screen, GRAY, cell_rect)

                pygame.draw.rect(self.screen, BLACK, cell_rect, 1)

    def draw_ship_sprites(self):
        for ship in self.placed_ships:
            original_image = self.ship_images.get(ship['name'])
            if original_image:
                ship_details = next((s for s in self.ships_to_place if s['name'] == ship['name']), None)
                if not ship_details: continue
                length = ship_details['length']

                if ship['orientation'] == 'H':
                    scaled_image = pygame.transform.scale(original_image, (length * CELL_SIZE, CELL_SIZE))
                else: # 'V'
                    rotated_image = pygame.transform.rotate(original_image, 90)
                    scaled_image = pygame.transform.scale(rotated_image, (CELL_SIZE, length * CELL_SIZE))
                self.screen.blit(scaled_image, (self.own_board_rect.x + ship['start_col'] * CELL_SIZE, self.own_board_rect.y + ship['start_row'] * CELL_SIZE))

    def draw_ship_placement_preview(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place): return
        ship = self.ships_to_place[self.current_ship_index]
        if self.own_board_rect.collidepoint(mouse_pos):
            col, row = (mouse_pos[0] - self.own_board_rect.x) // CELL_SIZE, (mouse_pos[1] - self.own_board_rect.y) // CELL_SIZE
            can_place, cells = self.check_placement(ship, row, col)
            color = GREEN if can_place else RED
            for r, c in cells:
                preview_rect = pygame.Rect(self.own_board_rect.x + c * CELL_SIZE, self.own_board_rect.y + r * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                
                s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                s.fill((color[0], color[1], color[2], 128))
                self.screen.blit(s, preview_rect.topleft)


    def draw_ship_list(self):
        y_offset = 50
        x_offset = WINDOW_WIDTH // 2 - 150
        title_surf = self.big_font.render("Place Your Fleet (R to rotate)", True, BLACK)
        self.screen.blit(title_surf, (x_offset, y_offset))
        y_offset += 50

        for i, ship in enumerate(self.ships_to_place):
            color = GREEN if ship['placed'] else (BLUE if i == self.current_ship_index else BLACK)
            text = f"{ship['name']} ({ship['length']})"
            if i == self.current_ship_index and not ship['placed']:
                 text += f" - Placing ({self.ship_orientation})"

            self.screen.blit(self.font.render(text, True, color), (x_offset, y_offset + i * 30))

if __name__ == '__main__':
    game = BattleshipGUI()
    game.run()