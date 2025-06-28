import pygame
import sys
import json
import time
from client_network import BattleshipClient

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

class BattleshipGUI:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Battleship Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.big_font = pygame.font.Font(None, 36)
        
        self.client = BattleshipClient()
        self.client.add_message_callback(self.handle_server_message)
        
        self.game_phase = "connecting"
        self.own_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.opponent_board = [['.' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.your_turn = False
        self.player_number = None
        self.status_message = "Connecting to server..."
        
        # --- MODIFIED: Added state for scoreboard and timer ---
        self.own_sunk_ships = []
        self.opponent_sunk_ships = []
        self.turn_start_time = 0
        self.turn_duration = 0
        
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

    def handle_server_message(self, message):
        msg_type = message.get('type')
        
        # --- ADDED: Handle sunk ship and timer info ---
        sunk_info = message.get('sunk_ship_info')
        if sunk_info:
            if sunk_info['player'] == self.player_number:
                if sunk_info['ship_name'] not in self.own_sunk_ships: self.own_sunk_ships.append(sunk_info['ship_name'])
            else:
                if sunk_info['ship_name'] not in self.opponent_sunk_ships: self.opponent_sunk_ships.append(sunk_info['ship_name'])

        if 'turn_start_time' in message:
            self.turn_start_time = message['turn_start_time']
            self.turn_duration = message['turn_duration']

        if msg_type in ['game_start', 'attack_result', 'opponent_attack', 'turn_timeout']:
            self.your_turn = message.get('your_turn', False)

        if msg_type == 'waiting':
            self.game_phase = "waiting"
            self.status_message = message['message']
        elif msg_type == 'game_found':
            self.game_phase = "placing_ships"
            self.player_number = message['player_number']
            self.status_message = f"You are Player {self.player_number}. Place your ships!"
        elif msg_type == 'ships_placed':
            self.status_message = "Ships placed! Waiting for opponent..." if message['success'] else message['message']
        elif msg_type == 'game_start':
            self.game_phase = "playing"
            self.status_message = message['message']
        elif msg_type == 'attack_result':
            self.status_message = f"Attack result: {message['result']}"
            if message.get('game_over'): self.game_phase = "game_over"
        elif msg_type == 'opponent_attack':
            self.status_message = f"Opponent attacked: {message['result']}"
            if message.get('game_over'): self.game_phase = "game_over"
        elif msg_type == 'turn_timeout':
            self.status_message = message['message']
        elif msg_type == 'game_over':
            self.game_phase = "game_over"
            winner_text = message['winner']
            if (winner_text == "Player 1" and self.player_number == 1) or \
               (winner_text == "Player 2" and self.player_number == 2):
                self.status_message = "Game Over: You won!"
            else:
                self.status_message = f"Game Over: {winner_text} won!"
        elif msg_type == 'opponent_disconnected':
            self.game_phase = "game_over"
            self.status_message = message['message']
        elif msg_type == 'game_state':
            self.own_board = message['own_board']
            self.opponent_board = message['opponent_board']

    def connect_to_server(self):
        if self.client.connect():
            self.client.join_game()
        else:
            self.status_message = "Failed to connect. Please restart the application."

    def draw_board(self, board, board_rect, title, clickable=False):
        title_surface = self.big_font.render(title, True, BLACK)
        self.screen.blit(title_surface, (board_rect.centerx - title_surface.get_width() / 2, board_rect.top - 40))
        
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                cell_rect = pygame.Rect(board_rect.x + col * CELL_SIZE, board_rect.y + row * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                cell_value = board[row][col]
                
                # --- MODIFIED: Color for misses is now GRAY ---
                if cell_value == '.': color = WHITE
                elif cell_value == 'X': color = RED
                elif cell_value == 'O': color = GRAY # Changed from BLUE
                else: color = SHIP_COLORS.get(cell_value, LIGHT_GRAY)
                
                pygame.draw.rect(self.screen, color, cell_rect)
                pygame.draw.rect(self.screen, BLACK, cell_rect, 1)

    def draw_ship_placement_preview(self, mouse_pos):
        if self.current_ship_index >= len(self.ships_to_place):
            return
        
        ship = self.ships_to_place[self.current_ship_index]
        if ship['placed']:
            return
        
        # Convert mouse position to board coordinates
        if self.own_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.own_board_rect.x
            rel_y = mouse_pos[1] - self.own_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                # Check if ship can be placed
                can_place = True
                cells_to_highlight = []
                
                if self.ship_orientation == 'H':
                    if col + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for c in range(col, col + ship['length']):
                            if self.own_board[row][c] != '.':
                                can_place = False
                            cells_to_highlight.append((row, c))
                else:  # Vertical
                    if row + ship['length'] > BOARD_SIZE:
                        can_place = False
                    else:
                        for r in range(row, row + ship['length']):
                            if self.own_board[r][col] != '.':
                                can_place = False
                            cells_to_highlight.append((r, col))
                
                # Draw preview
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
        
        # Convert mouse position to board coordinates
        if self.own_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.own_board_rect.x
            rel_y = mouse_pos[1] - self.own_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                # Check if ship can be placed
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
                    # Place the ship
                    ship_char = ship['name'][0]
                    for r, c in cells_to_place:
                        self.own_board[r][c] = ship_char
                    
                    ship['placed'] = True
                    self.placed_ships.append({
                        'name': ship['name'],
                        'start_row': row if self.ship_orientation == 'V' else row,
                        'start_col': col if self.ship_orientation == 'H' else col,
                        'orientation': self.ship_orientation
                    })
                    
                    # Move to next ship
                    self.current_ship_index += 1
                    
                    # Check if all ships are placed
                    if self.current_ship_index >= len(self.ships_to_place):
                        self.client.place_ships(self.placed_ships)
                        self.status_message = "All ships placed! Waiting for opponent..."

    def attack_opponent(self, mouse_pos):
        if not self.your_turn or self.game_phase != "playing":
            return
        
        # Convert mouse position to board coordinates
        if self.opponent_board_rect.collidepoint(mouse_pos):
            rel_x = mouse_pos[0] - self.opponent_board_rect.x
            rel_y = mouse_pos[1] - self.opponent_board_rect.y
            col = rel_x // CELL_SIZE
            row = rel_y // CELL_SIZE
            
            if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
                # Check if cell was already attacked
                if self.opponent_board[row][col] in ['.']:
                    self.client.attack(row, col)

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
        
        if self.game_phase == "playing":
            # --- MODIFIED: Display turn and timer ---
            turn_text = "Your Turn" if self.your_turn else "Opponent's Turn"
            turn_color = GREEN if self.your_turn else RED
            
            time_left = self.turn_duration - (time.time() - self.turn_start_time)
            if time_left < 0: time_left = 0
            
            full_text = f"{turn_text} ({int(time_left)}s)"
            turn_surface = self.font.render(full_text, True, turn_color)
            self.screen.blit(turn_surface, (WINDOW_WIDTH / 2 - turn_surface.get_width() / 2, 50))
    
    # --- ADDED: New method to draw the scoreboard ---
    def draw_scoreboard(self):
        scoreboard_y = self.own_board_rect.bottom + 20
        
        def render_sunk_list(title, ships, x_pos, y_pos, color):
            title_surf = self.font.render(title, True, BLACK)
            self.screen.blit(title_surf, (x_pos, y_pos))
            for i, ship_name in enumerate(ships):
                ship_surf = self.font.render(ship_name, True, color)
                # Draw a strikethrough
                pygame.draw.line(self.screen, color, (x_pos, y_pos + (i + 1) * 25 + 10), (x_pos + ship_surf.get_width(), y_pos + (i + 1) * 25 + 10), 2)
                self.screen.blit(ship_surf, (x_pos, y_pos + (i + 1) * 25))

        render_sunk_list("Your Sunk Ships", self.own_sunk_ships, self.own_board_rect.left, scoreboard_y, RED)
        render_sunk_list("Opponent Sunk Ships", self.opponent_sunk_ships, self.opponent_board_rect.left, scoreboard_y, GREEN)

    def run(self):
        self.connect_to_server()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r and self.game_phase == "placing_ships": self.ship_orientation = 'V' if self.ship_orientation == 'H' else 'H'
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.game_phase == "placing_ships": self.place_ship(event.pos)
                        elif self.game_phase == "playing": self.attack_opponent(event.pos)
            
            self.screen.fill(LIGHT_GRAY)
            self.draw_status()
            
            if self.game_phase == "placing_ships":
                self.draw_board(self.own_board, self.own_board_rect, "Your Board")
                self.draw_ship_list()
                self.draw_ship_placement_preview(pygame.mouse.get_pos())
            elif self.game_phase in ["playing", "game_over"]:
                self.draw_board(self.own_board, self.own_board_rect, "Your Board")
                self.draw_board(self.opponent_board, self.opponent_board_rect, "Opponent's Board", True)
                # --- ADDED: Call to draw scoreboard ---
                self.draw_scoreboard()
            
            pygame.display.flip()
            self.clock.tick(60)
        
        self.client.disconnect()
        pygame.quit()
        sys.exit()

if __name__ == '__main__':
    game = BattleshipGUI()
    game.run()

