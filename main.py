# main.py
import pygame
import sys
import json
import time
import random
from battleship.client_network import BattleshipClient

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
BOARD_SIZE = 10
CELL_SIZE = 40
BOARD_MARGIN = 50
SHIP_COLORS = {
    'C': (142, 68, 173), # Carrier - Purple
    'B': (46, 134, 193), # Battleship - Blue
    'R': (241, 196, 15), # Cruiser - Yellow
    'S': (39, 174, 96),  # Submarine - Green
    'D': (231, 76, 60)   # Destroyer - Red
}

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 100, 200)
RED = (200, 0, 0)
GREEN = (0, 200, 0)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)

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
                    return True # Indicate enter was pressed
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
        pygame.display.set_caption("Battleship Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.big_font = pygame.font.Font(None, 36)
        self.hit_marker_font = pygame.font.Font(None, int(CELL_SIZE * 1.2))
        
        self.client = BattleshipClient()
        self.client.add_message_callback(self.handle_server_message)
        
        self.game_phase = "main_menu" # Initial phase
        
        # Game State
        self.own_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.opponent_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.your_turn = False
        self.player_number = None
        self.status_message = ""
        self.player_name = ""
        self.opponent_name = ""
        self.current_turn_player_name = None
        
        self.own_sunk_ships = []
        self.opponent_sunk_ships = []
        self.turn_start_time = 0
        self.turn_duration = 0
        self.room_code = ""
        self.game_list = [] # For spectator mode

        # Spectator Boards
        self.spectate_board_p1 = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.spectate_board_p2 = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.is_spectator = False
        self.player1_name_spectate = "Player 1"
        self.player2_name_spectate = "Player 2"


        # Ship Placement
        self.ships_to_place = [
            {"name": "Carrier", "length": 5, "placed": False},
            {"name": "Battleship", "length": 4, "placed": False},
            {"name": "Cruiser", "length": 3, "placed": False},
            {"name": "Submarine", "length": 3, "placed": False},
            {"name": "Destroyer", "length": 2, "placed": False}
        ]
        self.current_ship_index = 0
        self.ship_orientation = 'H'
        self.placed_ships = []
        
        self.own_board_rect = pygame.Rect(BOARD_MARGIN, BOARD_MARGIN + 100, BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)
        self.opponent_board_rect = pygame.Rect(WINDOW_WIDTH - BOARD_MARGIN - BOARD_SIZE * CELL_SIZE, BOARD_MARGIN + 100, BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)

        # UI Elements
        self.main_menu_buttons = []
        self.host_game_inputs = {}
        self.join_game_inputs = {}
        self.spectate_game_buttons = []

        self.setup_ui_elements()
        self.connect_to_server() # Connect on startup

    def setup_ui_elements(self):
        # Main Menu
        btn_width, btn_height = 200, 60
        spacing = 20
        start_y = WINDOW_HEIGHT // 2 - (btn_height * 2 + spacing * 1.5)

        self.main_menu_buttons = [
            Button(WINDOW_WIDTH // 2 - btn_width // 2, start_y, btn_width, btn_height, "Host Game", BLUE, LIGHT_GRAY, self.go_to_host_game),
            Button(WINDOW_WIDTH // 2 - btn_width // 2, start_y + btn_height + spacing, btn_width, btn_height, "Join Game", BLUE, LIGHT_GRAY, self.go_to_join_game),
            Button(WINDOW_WIDTH // 2 - btn_width // 2, start_y + (btn_height + spacing) * 2, btn_width, btn_height, "Quick Play", BLUE, LIGHT_GRAY, self.start_quick_play),
            Button(WINDOW_WIDTH // 2 - btn_width // 2, start_y + (btn_height + spacing) * 3, btn_width, btn_height, "Spectate Game", BLUE, LIGHT_GRAY, self.go_to_spectate_game)
        ]

        # Host Game Screen
        self.host_game_inputs['name_input'] = InputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 50, 300, 40, '')
        self.host_game_inputs['host_button'] = Button(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Host Game", GREEN, LIGHT_GRAY, self.host_private_game)
        self.host_game_inputs['back_button'] = Button(50, 50, 100, 40, "Back", GRAY, LIGHT_GRAY, self.go_to_main_menu)


        # Join Game Screen
        self.join_game_inputs['name_input'] = InputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 100, 300, 40, '')
        self.join_game_inputs['code_input'] = InputBox(WINDOW_WIDTH // 2 - 150, WINDOW_HEIGHT // 2 - 40, 300, 40, 'Room Code')
        self.join_game_inputs['join_button'] = Button(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Join Game", GREEN, LIGHT_GRAY, self.join_private_game)
        self.join_game_inputs['back_button'] = Button(50, 50, 100, 40, "Back", GRAY, LIGHT_GRAY, self.go_to_main_menu)

        # Spectate Game Screen
        self.spectate_game_buttons.append(Button(50, 50, 100, 40, "Back", GRAY, LIGHT_GRAY, self.go_to_main_menu))
        self.spectate_game_buttons.append(Button(WINDOW_WIDTH - 150, 50, 100, 40, "Refresh", BLUE, LIGHT_GRAY, self.refresh_game_list))

    def handle_server_message(self, message):
        msg_type = message.get('type')
        
        sunk_info = message.get('sunk_ship_info')
        if sunk_info:
            if self.is_spectator:
                # Spectators don't have 'own' or 'opponent' player numbers directly
                # The server sends which player's ship was sunk (1 or 2)
                pass # Sunk ship info for spectators will be handled by game_state directly for board updates
            elif sunk_info['player'] == self.client.game_state['player_number']: # This client's ship was sunk
                if sunk_info['ship_name'] not in self.own_sunk_ships: self.own_sunk_ships.append(sunk_info['ship_name'])
            else: # Opponent's ship was sunk
                if sunk_info['ship_name'] not in self.opponent_sunk_ships: self.opponent_sunk_ships.append(sunk_info['ship_name'])

        if 'turn_start_time' in message:
            self.turn_start_time = message['turn_start_time']
            self.turn_duration = message['turn_duration']

        if msg_type in ['game_start', 'attack_result', 'opponent_attack', 'turn_timeout']:
            self.your_turn = message.get('your_turn', False)
            self.current_turn_player_name = message.get('current_turn_player_name', self.current_turn_player_name)

        if msg_type == 'waiting':
            self.game_phase = "waiting_room"
            self.status_message = message['message']
            self.room_code = message.get('room_code', '')
        elif msg_type == 'room_code': # Specifically for host to get the code
            self.room_code = message['code']
        elif msg_type == 'room_join_status':
            if message['success']:
                # The 'game_found' message will follow this for actual game setup
                pass
            else:
                self.status_message = message['message']
                # Stay on join game screen if failed
                self.game_phase = "join_game"
        elif msg_type == 'game_found':
            self.game_phase = "placing_ships"
            self.player_number = message['player_number']
            self.player_name = message.get('player_name', '')
            self.opponent_name = message.get('opponent_name', '')
            self.room_code = message.get('room_code', '')
            self.status_message = f"You are Player {self.player_number} ({self.player_name}). Place your ships!"
            self.reset_ship_placement()
        elif msg_type == 'ships_placed':
            self.status_message = "Ships placed! Waiting for opponent..." if message['success'] else message['message']
        elif msg_type == 'game_start':
            self.game_phase = "playing"
            self.status_message = message['message']
            self.player_name = self.client.game_state['player_name']
            self.opponent_name = self.client.game_state['opponent_name']
            self.current_turn_player_name = message.get('current_turn_player_name')
            self.is_spectator = False # Ensure spectator flag is false if a player

        elif msg_type == 'attack_result':
            self.status_message = f"Attack result: {message['result']}"
            if message.get('success'):
                row, col = message['row'], message['col']
                result = message['result']
                if "sunk" in result or "Hit" in result:
                    self.opponent_board[row][col] = 'X'
                elif "Miss" in result:
                    self.opponent_board[row][col] = 'O'
            if message.get('game_over'):
                self.game_phase = "game_over"

        elif msg_type == 'opponent_attack':
            self.status_message = f"Opponent attacked: {message['result']}"
            row, col = message['row'], message['col']
            result = message['result']
            if "sunk" in result or "Hit" in result:
                self.own_board[row][col] = 'X'
            elif "Miss" in result:
                self.own_board[row][col] = 'O'
            if message.get('game_over'):
                self.game_phase = "game_over"
                
        elif msg_type == 'turn_timeout':
            self.status_message = message['message']
        elif msg_type == 'game_over':
            self.game_phase = "game_over"
            winner_text = message['winner']
            if self.is_spectator:
                self.status_message = f"Game Over: {winner_text} won!"
            elif (winner_text == self.player_name): # If the winner is this player's name
                self.status_message = "Game Over: You won!"
            else: # Opponent won, or game ended for other reasons
                self.status_message = f"Game Over: {winner_text} won!"

        elif msg_type == 'opponent_disconnected':
            self.game_phase = "game_over"
            self.status_message = message['message']
        elif msg_type == 'game_state':
            # Handle game state for both players and spectators
            if self.is_spectator:
                self.spectate_board_p1 = message['player1_board']
                self.spectate_board_p2 = message['player2_board']
                self.player1_name_spectate = message.get('player1_name', 'Player 1')
                self.player2_name_spectate = message.get('player2_name', 'Player 2')
                self.current_turn_player_name = message.get('current_turn_player_name')
                self.status_message = f"Spectating {self.player1_name_spectate} vs {self.player2_name_spectate}"
                if message.get('game_started'):
                    self.game_phase = "spectating"
            else:
                self.own_board = message['own_board']
                self.opponent_board = message['opponent_board']
                self.player_name = message.get('player_name', self.player_name)
                self.opponent_name = message.get('opponent_name', self.opponent_name)
                self.your_turn = message.get('your_turn', self.your_turn)
                self.current_turn_player_name = message.get('current_turn_player_name')

        elif msg_type == 'game_list':
            self.game_list = message['games']
            self.status_message = f"Available public games: {len(self.game_list)}"
            # Now draw the game list in spectate_game phase
        elif msg_type == 'spectate_start':
            self.is_spectator = True
            self.game_phase = "spectating"
            self.status_message = message.get('message', "Spectating game...")
            self.player1_name_spectate = message.get('player1_name', 'Player 1')
            self.player2_name_spectate = message.get('player2_name', 'Player 2')
            self.current_turn_player_name = message.get('current_turn_player_name')
            
    def reset_game_state(self):
        self.own_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.opponent_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.your_turn = False
        self.player_number = None
        self.player_name = ""
        self.opponent_name = ""
        self.current_turn_player_name = None
        self.own_sunk_ships = []
        self.opponent_sunk_ships = []
        self.turn_start_time = 0
        self.turn_duration = 0
        self.room_code = ""
        self.is_spectator = False
        self.spectate_board_p1 = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.spectate_board_p2 = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.player1_name_spectate = "Player 1"
        self.player2_name_spectate = "Player 2"
        self.reset_ship_placement()

    def reset_ship_placement(self):
        self.ships_to_place = [
            {"name": "Carrier", "length": 5, "placed": False},
            {"name": "Battleship", "length": 4, "placed": False},
            {"name": "Cruiser", "length": 3, "placed": False},
            {"name": "Submarine", "length": 3, "placed": False},
            {"name": "Destroyer", "length": 2, "placed": False}
        ]
        self.current_ship_index = 0
        self.ship_orientation = 'H'
        self.placed_ships = []
        # Clear own board in case of re-entry
        self.own_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


    def connect_to_server(self):
        self.status_message = "Connecting to server..."
        if self.client.connect():
            self.status_message = "Connected to server."
        else:
            self.status_message = "Failed to connect. Please restart the application."
            self.game_phase = "error" # A new error phase to indicate connection failure

    # Navigation methods
    def go_to_main_menu(self):
        self.reset_game_state()
        self.game_phase = "main_menu"
        self.status_message = "Welcome to Battleship!"

    def go_to_host_game(self):
        self.reset_game_state()
        self.game_phase = "host_game"
        self.status_message = "Enter your name to host a private game."
        self.host_game_inputs['name_input'].text = '' # FIX: Changed from random name
        self.host_game_inputs['name_input'].txt_surface = self.host_game_inputs['name_input'].font.render(self.host_game_inputs['name_input'].text, True, self.host_game_inputs['name_input'].color)


    def go_to_join_game(self):
        self.reset_game_state()
        self.game_phase = "join_game"
        self.status_message = "Enter your name and room code to join a private game."
        self.join_game_inputs['name_input'].text = '' # FIX: Changed from random name
        self.join_game_inputs['name_input'].txt_surface = self.join_game_inputs['name_input'].font.render(self.join_game_inputs['name_input'].text, True, self.join_game_inputs['name_input'].color)
        self.join_game_inputs['code_input'].text = ''
        self.join_game_inputs['code_input'].txt_surface = self.join_game_inputs['code_input'].font.render(self.join_game_inputs['code_input'].text, True, self.join_game_inputs['code_input'].color)

    def go_to_spectate_game(self):
        self.reset_game_state()
        self.game_phase = "spectate_game"
        self.status_message = "Fetching public games..."
        self.client.get_game_list()

    # Game actions
    def host_private_game(self):
        player_name = self.host_game_inputs['name_input'].get_text().strip()
        if player_name:
            self.player_name = player_name
            self.client.host_game(player_name)
            self.status_message = "Hosting game... waiting for opponent."
            self.game_phase = "waiting_room"
        else:
            self.status_message = "Please enter your name."

    def join_private_game(self):
        player_name = self.join_game_inputs['name_input'].get_text().strip()
        room_code = self.join_game_inputs['code_input'].get_text().strip()
        if player_name and room_code:
            self.player_name = player_name
            self.client.join_private_game(player_name, room_code)
            self.status_message = "Attempting to join game..."
        else:
            self.status_message = "Please enter your name and the room code."
    
    def start_quick_play(self):
        self.reset_game_state()
        self.client.quick_play()
        self.game_phase = "waiting_room"
        self.status_message = "Searching for a quick play opponent..."

    def refresh_game_list(self):
        self.status_message = "Refreshing game list..."
        self.client.get_game_list()

    def select_spectate_game(self, game_id):
        self.reset_game_state()
        self.client.spectate_game(game_id)
        self.status_message = "Joining as spectator..."
        self.is_spectator = True # Set spectator flag immediately

    def draw_board(self, board, board_rect, title, clickable=False):
        title_surface = self.big_font.render(title, True, BLACK)
        self.screen.blit(title_surface, (board_rect.centerx - title_surface.get_width() / 2, board_rect.top - 40))
        
        for row_idx in range(BOARD_SIZE):
            for col_idx in range(BOARD_SIZE):
                cell_rect = pygame.Rect(board_rect.x + col_idx * CELL_SIZE, board_rect.y + row_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                cell_value = board[row_idx][col_idx]
                
                if cell_value == '.': color = WHITE
                elif cell_value == 'X': color = RED
                elif cell_value == 'O': color = GRAY
                else: color = SHIP_COLORS.get(cell_value, LIGHT_GRAY) # For ship cells
                
                pygame.draw.rect(self.screen, color, cell_rect)
                pygame.draw.rect(self.screen, BLACK, cell_rect, 1)

                if cell_value == 'X':
                    hit_surface = self.hit_marker_font.render('X', True, BLACK)
                    hit_rect = hit_surface.get_rect(center=cell_rect.center)
                    self.screen.blit(hit_surface, hit_rect)

    def draw_ship_placement_preview(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place):
            return
        
        ship = self.ships_to_place[self.current_ship_index]
        if ship['placed']:
            return
        
        if self.own_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.own_board_rect.x
            rel_y = mouse_pos[1] - self.own_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                can_place = True
                cells_to_highlight = []
                
                if self.ship_orientation == 'H':
                    if col + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for c in range(col, col + ship['length']):
                            # Check if the target cell is part of another ship
                            if self.own_board[row][c] != '.':
                                can_place = False
                            cells_to_highlight.append((row, c))
                else:  # Vertical
                    if row + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for r in range(row, row + ship['length']):
                            # Check if the target cell is part of another ship
                            if self.own_board[r][col] != '.':
                                can_place = False
                            cells_to_highlight.append((r, col))
                
                color = GREEN if can_place else RED
                for r, c in cells_to_highlight:
                    cell_rect = pygame.Rect(
                        self.own_board_rect.x + c * CELL_SIZE,
                        self.own_board_rect.y + r * CELL_SIZE,
                        CELL_SIZE,
                        CELL_SIZE
                    )
                    pygame.draw.rect(self.screen, color, cell_rect, 3)

    def place_ship(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place):
            return
        
        ship = self.ships_to_place[self.current_ship_index]
        if ship['placed']:
            return
        
        if self.own_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.own_board_rect.x
            rel_y = mouse_pos[1] - self.own_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                can_place = True
                cells_to_place = []
                
                if self.ship_orientation == 'H':
                    if col + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for c in range(col, col + ship['length']):
                            if self.own_board[row][c] != '.':
                                can_place = False
                            cells_to_place.append((row, c))
                else:  # Vertical
                    if row + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for r in range(row, row + ship['length']):
                            if self.own_board[r][col] != '.':
                                can_place = False
                            cells_to_place.append((r, col))
                
                if can_place:
                    ship_char = ship['name'][0]
                    for r, c in cells_to_place:
                        self.own_board[r][c] = ship_char
                    
                    ship['placed'] = True
                    self.placed_ships.append({
                        'name': ship['name'],
                        'start_row': row,
                        'start_col': col,
                        'orientation': self.ship_orientation
                    })
                    
                    self.current_ship_index += 1
                    
                    if self.current_ship_index >= len(self.ships_to_place):
                        self.client.place_ships(self.placed_ships)
                        self.status_message = "All ships placed! Waiting for opponent..."

    def attack_opponent(self, mouse_pos):
        if not self.your_turn or self.game_phase != "playing":
            self.status_message = "Not your turn or game not in playing phase!"
            return
        
        if self.opponent_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.opponent_board_rect.x
            rel_y = mouse_pos[1] - self.opponent_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                # Only allow attacking if the cell hasn't been attacked yet
                if self.opponent_board[row][col] == '.':
                    self.client.attack(row, col)
                else:
                    self.status_message = "This cell has already been attacked!"

    def draw_ship_list(self):
        y_offset = 50
        for i, ship in enumerate(self.ships_to_place):
            color = GREEN if ship['placed'] else (RED if i == self.current_ship_index else BLACK)
            text = f"{ship['name']} ({ship['length']})"
            if i == self.current_ship_index and not ship['placed']:
                text += f" - {self.ship_orientation}"
            
            ship_surface = self.font.render(text, True, color)
            self.screen.blit(ship_surface, (WINDOW_WIDTH // 2 - 100, y_offset + i * 30))

    def draw_status(self):
        status_surface = self.big_font.render(self.status_message, True, BLACK)
        self.screen.blit(status_surface, (WINDOW_WIDTH / 2 - status_surface.get_width() / 2, 10))
        
        if self.game_phase == "playing" or self.game_phase == "spectating":
            if not self.is_spectator:
                turn_text = f"Your Turn ({self.player_name})" if self.your_turn else f"Opponent's Turn ({self.opponent_name})"
                turn_color = GREEN if self.your_turn else RED
            else: # Spectator mode
                turn_text = f"Current Turn: {self.current_turn_player_name}"
                turn_color = BLUE

            time_left = self.turn_duration - (time.time() - self.turn_start_time)
            if time_left < 0: time_left = 0
            
            full_text = f"{turn_text} ({int(time_left)}s left)"
            turn_surface = self.font.render(full_text, True, turn_color)
            self.screen.blit(turn_surface, (WINDOW_WIDTH / 2 - turn_surface.get_width() / 2, 50))
    
    def draw_scoreboard(self):
        scoreboard_y = self.own_board_rect.bottom + 20
        
        def render_sunk_list(title, ships, x_pos, y_pos, color):
            title_surf = self.font.render(title, True, BLACK)
            self.screen.blit(title_surf, (x_pos, y_pos))
            for i, ship_name in enumerate(ships):
                ship_surf = self.font.render(ship_name, True, color)
                pygame.draw.line(self.screen, color, (x_pos, y_pos + (i + 1) * 25 + 10), (x_pos + ship_surf.get_width(), y_pos + (i + 1) * 25 + 10), 2)
                self.screen.blit(ship_surf, (x_pos, y_pos + (i + 1) * 25))

        # Only display relevant scoreboard for players/spectators
        if not self.is_spectator:
            render_sunk_list("Your Sunk Ships", self.own_sunk_ships, self.own_board_rect.left, scoreboard_y, RED)
            render_sunk_list("Opponent Sunk Ships", self.opponent_sunk_ships, self.opponent_board_rect.left, scoreboard_y, GREEN)
        else: # For spectators, perhaps list all sunk ships, or no specific "sunk" list
            # You could add a combined list here if desired, or just rely on board markers
            pass


    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                
                # Event handling based on game phase
                if self.game_phase == "main_menu":
                    for button in self.main_menu_buttons:
                        button.handle_event(event)
                elif self.game_phase == "host_game":
                    self.host_game_inputs['name_input'].handle_event(event)
                    self.host_game_inputs['host_button'].handle_event(event)
                    self.host_game_inputs['back_button'].handle_event(event)
                elif self.game_phase == "join_game":
                    self.join_game_inputs['name_input'].handle_event(event)
                    self.join_game_inputs['code_input'].handle_event(event)
                    self.join_game_inputs['join_button'].handle_event(event)
                    self.join_game_inputs['back_button'].handle_event(event)
                elif self.game_phase == "spectate_game":
                    for button in self.spectate_game_buttons:
                        button.handle_event(event)
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        # Handle clicks on game list items
                        mouse_x, mouse_y = event.pos
                        list_start_y = WINDOW_HEIGHT // 2 - (len(self.game_list) * 30 // 2)
                        for i, game_info in enumerate(self.game_list):
                            text_rect = pygame.Rect(WINDOW_WIDTH // 2 - 200, list_start_y + i * 30, 400, 25)
                            if text_rect.collidepoint(mouse_x, mouse_y):
                                self.select_spectate_game(game_info['game_id'])
                                break
                elif self.game_phase == "placing_ships":
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_r: self.ship_orientation = 'V' if self.ship_orientation == 'H' else 'H'
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if event.button == 1: self.place_ship(event.pos)
                elif self.game_phase == "playing":
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if event.button == 1: self.attack_opponent(event.pos)
            
            self.screen.fill(LIGHT_GRAY)
            self.draw_status()
            
            if self.game_phase == "main_menu":
                for button in self.main_menu_buttons:
                    button.draw(self.screen)
            elif self.game_phase == "host_game":
                name_label = self.font.render("Your Name:", True, BLACK)
                self.screen.blit(name_label, (self.host_game_inputs['name_input'].rect.x, self.host_game_inputs['name_input'].rect.y - 30))
                self.host_game_inputs['name_input'].draw(self.screen)
                self.host_game_inputs['host_button'].draw(self.screen)
                self.host_game_inputs['back_button'].draw(self.screen)
            elif self.game_phase == "join_game":
                name_label = self.font.render("Your Name:", True, BLACK)
                self.screen.blit(name_label, (self.join_game_inputs['name_input'].rect.x, self.join_game_inputs['name_input'].rect.y - 30))
                code_label = self.font.render("Room Code:", True, BLACK)
                self.screen.blit(code_label, (self.join_game_inputs['code_input'].rect.x, self.join_game_inputs['code_input'].rect.y - 30))
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
                self.host_game_inputs['back_button'].draw(self.screen) # Use host game back button for simplicity
            elif self.game_phase == "spectate_game":
                for button in self.spectate_game_buttons:
                    button.draw(self.screen)
                
                if self.game_list:
                    list_title_surf = self.big_font.render("Available Public Games", True, BLACK)
                    self.screen.blit(list_title_surf, (WINDOW_WIDTH // 2 - list_title_surf.get_width() // 2, WINDOW_HEIGHT // 2 - (len(self.game_list) * 30 // 2) - 50))
                    
                    list_start_y = WINDOW_HEIGHT // 2 - (len(self.game_list) * 30 // 2)
                    for i, game_info in enumerate(self.game_list):
                        game_text = f"Game {i+1}: {game_info['player1_name']} vs {game_info['player2_name']}"
                        game_surf = self.font.render(game_text, True, BLACK)
                        text_rect = game_surf.get_rect(center=(WINDOW_WIDTH // 2, list_start_y + i * 30 + game_surf.get_height() // 2))
                        pygame.draw.rect(self.screen, LIGHT_GRAY, text_rect.inflate(10, 5)) # Add background to make clickable areas clear
                        self.screen.blit(game_surf, text_rect)
                else:
                    no_games_surf = self.big_font.render("No public games available.", True, BLACK)
                    self.screen.blit(no_games_surf, (WINDOW_WIDTH // 2 - no_games_surf.get_width() // 2, WINDOW_HEIGHT // 2))

            elif self.game_phase == "placing_ships":
                self.draw_board(self.own_board, self.own_board_rect, f"{self.player_name}'s Board")
                self.draw_ship_list()
                self.draw_ship_placement_preview(pygame.mouse.get_pos())
            elif self.game_phase == "playing":
                self.draw_board(self.own_board, self.own_board_rect, f"{self.player_name}'s Board")
                self.draw_board(self.opponent_board, self.opponent_board_rect, f"{self.opponent_name}'s Board", True)
                self.draw_scoreboard()
            elif self.game_phase == "spectating":
                # Draw both player boards for spectators
                p1_board_rect = pygame.Rect(BOARD_MARGIN, BOARD_MARGIN + 100, BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)
                p2_board_rect = pygame.Rect(WINDOW_WIDTH - BOARD_MARGIN - BOARD_SIZE * CELL_SIZE, BOARD_MARGIN + 100, BOARD_SIZE * CELL_SIZE, BOARD_SIZE * CELL_SIZE)

                self.draw_board(self.spectate_board_p1, p1_board_rect, f"{self.player1_name_spectate}'s Board")
                self.draw_board(self.spectate_board_p2, p2_board_rect, f"{self.player2_name_spectate}'s Board")
                
                # Back to Main Menu button for spectators
                spectate_back_button = Button(50, 50, 100, 40, "Main Menu", GRAY, LIGHT_GRAY, self.go_to_main_menu)
                spectate_back_button.draw(self.screen)

            elif self.game_phase == "game_over":
                game_over_text = self.big_font.render(self.status_message, True, BLACK)
                self.screen.blit(game_over_text, (WINDOW_WIDTH // 2 - game_over_text.get_width() // 2, WINDOW_HEIGHT // 2 - 50))
                main_menu_button = Button(WINDOW_WIDTH // 2 - 100, WINDOW_HEIGHT // 2 + 50, 200, 50, "Main Menu", BLUE, LIGHT_GRAY, self.go_to_main_menu)
                main_menu_button.draw(self.screen)
                main_menu_button.handle_event(event) # To make the button clickable
            elif self.game_phase == "error":
                error_text = self.big_font.render(self.status_message, True, RED)
                self.screen.blit(error_text, (WINDOW_WIDTH // 2 - error_text.get_width() // 2, WINDOW_HEIGHT // 2 - 50))

            pygame.display.flip()
            self.clock.tick(60)
        
        self.client.disconnect()
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    game = BattleshipGUI()
    game.run()