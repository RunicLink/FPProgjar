# game_logic.py
import random

class BattleshipGame:
    def __init__(self):
        self.board_size = 10
        self.ships = {
            "AircraftCarrier": 5,
            "Battleship": 4,
            "Cruiser": 3,
            "Submarine": 3,
            "PatrolBoat": 2
        }
        self.player1_board = [['.' for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.player2_board = [['.' for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.player1_ships = {}
        self.player2_ships = {}

    def place_ship(self, player_board, player_ships, ship_name, ship_length, start_row, start_col, orientation):
        if orientation == 'H':
            if start_col + ship_length > self.board_size:
                return False
            for col in range(start_col, start_col + ship_length):
                if player_board[start_row][col] != '.':
                    return False
            for col in range(start_col, start_col + ship_length):
                player_board[start_row][col] = ship_name[0] 
            player_ships[ship_name] = {'positions': [(start_row, c) for c in range(start_col, start_col + ship_length)], 'hits': []}
        elif orientation == 'V':
            if start_row + ship_length > self.board_size:
                return False
            for row in range(start_row, start_row + ship_length):
                if player_board[row][start_col] != '.':
                    return False
            for row in range(start_row, start_row + ship_length):
                player_board[row][start_col] = ship_name[0]
            player_ships[ship_name] = {'positions': [(r, start_col) for r in range(start_row, start_row + ship_length)], 'hits': []}
        else:
            return False
        return True

    def auto_place_ships(self, player_board, player_ships):
        for ship_name, ship_length in self.ships.items():
            placed = False
            while not placed:
                orientation = random.choice(['H', 'V'])
                if orientation == 'H':
                    start_row = random.randint(0, self.board_size - 1)
                    start_col = random.randint(0, self.board_size - ship_length)
                else:
                    start_row = random.randint(0, self.board_size - ship_length)
                    start_col = random.randint(0, self.board_size - 1)
                
                temp_board = [row[:] for row in player_board]
                temp_ships = {}

                if self.place_ship(temp_board, temp_ships, ship_name, ship_length, start_row, start_col, orientation):
                    self.place_ship(player_board, player_ships, ship_name, ship_length, start_row, start_col, orientation)
                    placed = True


    def attack(self, opponent_board, opponent_ships, row, col):
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return "Invalid coordinates"
        if opponent_board[row][col] in ['X', 'O']:
            return "Already attacked"

        hit_char = opponent_board[row][col]
        if hit_char != '.':
            ship_name_hit = None
            for name, data in opponent_ships.items():
                if hit_char == name[0]:
                    if (row, col) in data['positions']:
                        ship_name_hit = name
                        data['hits'].append((row, col))
                        break
            
            opponent_board[row][col] = 'X' 
            
            if ship_name_hit:
                if len(opponent_ships[ship_name_hit]['hits']) == len(opponent_ships[ship_name_hit]['positions']):
                    return f"Hit and sunk {ship_name_hit}!"
                else:
                    return "Hit"
            else:
                return "Hit" 
        else:
            opponent_board[row][col] = 'O'
            return "Miss"

    def check_game_over(self, opponent_ships):
        if not opponent_ships:
            return False
            
        for ship_name, data in opponent_ships.items():
            if len(data['hits']) < len(data['positions']):
                return False
        return True

    def print_board(self, board):
        for row in board:
            print(" ".join(str(cell) for cell in row))


if __name__ == '__main__':
    game = BattleshipGame()
    
    p1_board = [['.' for _ in range(game.board_size)] for _ in range(game.board_size)]
    p1_ships = {}
    p2_board = [['.' for _ in range(game.board_size)] for _ in range(game.board_size)]
    p2_ships = {}

    game.auto_place_ships(p1_board, p1_ships)
    game.auto_place_ships(p2_board, p2_ships)

    print("Player 1 Board:")
    game.print_board(p1_board)
    print("\nPlayer 2 Board:")
    game.print_board(p2_board)

    print("\nAttacking Player 1's board at (0,0):")
    print(game.attack(p1_board, p1_ships, 0, 0))
    game.print_board(p1_board)

    if game.check_game_over(p1_ships):
        print("Player 1's ships are all sunk! Game Over.")
    else:
        print("Player 1's ships are not all sunk.")