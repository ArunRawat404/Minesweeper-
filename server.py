import socketio
import eventlet
import random
from datetime import datetime

# Initialize Socket.IO server
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

# Game state
game_state = {
    'players': {},
    'board_seed': None,
    'game_started': False,
    'game_finished': False
}

def get_player_id():
    return f"Player {'A' if len(game_state['players']) == 0 else 'B'}"

def reset_game():
    game_state['board_seed'] = None
    game_state['game_started'] = False
    game_state['game_finished'] = False

@sio.on('connect')
def handle_connect(sid, environ):
    # Reject new connections if the game is full
    if len(game_state['players']) >= 2:
        sio.emit('connection_error', {'message': 'Game is full'}, room=sid)
        sio.disconnect(sid)
        return 

    # Generate board seed on first connection
    if not game_state['board_seed']:
        game_state['board_seed'] = random.randint(1, 1000000)

    # Assign player ID and store player info
    player_id = get_player_id()
    game_state['players'][sid] = {
        'id': player_id,
        'finished_time': None,
        'connected_at': datetime.now()
    }

    # Notify player of connection
    sio.emit('player_connected', {
        'player_id': player_id,
        'board_seed': game_state['board_seed'],
        'total_players': len(game_state['players'])
    }, room=sid)

    # Start game if two players are connected
    if len(game_state['players']) == 2:
        game_state['game_started'] = True
        for p_sid in game_state['players']:
            sio.emit('game_start', {'board_seed': game_state['board_seed']}, room=p_sid)

@sio.on('player_finished')
def handle_player_finished(sid, data):
    if game_state['game_finished']:
        return

    # Record player's finish time
    game_state['players'][sid]['finished_time'] = data.get('game_time')

    # Get players who have finished
    finished_players = {p_sid: player for p_sid, player in game_state['players'].items() if player['finished_time']}

    # If all players finished
    if len(finished_players) == 2:
        game_state['game_finished'] = True

        # Determine winner (first to finish)
        try:
            winner = min(
                finished_players.items(),
                key=lambda x: datetime.strptime(x[1]['finished_time'], '%H:%M:%S')
            )[1]['id']
        except ValueError:
            winner = list(finished_players.values())[0]['id']

        # Prepare finish times for all players
        times = {player['id']: player['finished_time'] for player in game_state['players'].values()}

        # Broadcast game over to all players
        for p_sid in game_state['players']:
            sio.emit('game_over', {'winner': winner, 'times': times}, room=p_sid)

@sio.on('disconnect')
def handle_disconnect(sid):
    # Remove player from game state
    if sid in game_state['players']:
        del game_state['players'][sid]

    # Reset game if less than 2 players remain
    if len(game_state['players']) < 2:
        reset_game()

        # Notify remaining player that the game has ended due to disconnection
        for p_sid in game_state['players']:
            sio.emit('game_over', {'winner': None, 'times': {}} , room=p_sid)

@sio.on('error')
def handle_error(sid, error):
    print(f"Socket error for {sid}: {error}")
    sio.emit('connection_error', {'message': 'An error occurred'}, room=sid)

if __name__ == '__main__':
    print("Starting server on localhost:5000")
    eventlet.wsgi.server(eventlet.listen(('localhost', 5000)), app)
