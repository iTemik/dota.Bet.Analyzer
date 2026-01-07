from flask import Flask, Response, stream_with_context, jsonify
from celery import Celery
import redis
import json
import time

from backend.config import Config
from . import __version__, create_app

app = create_app(__name__)

# Celery configuration

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Redis for progress storage
redis_client = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=1)

@celery.task(bind=True)
def heavy_calculation_task(self, task_id):
    """Celery task for heavy calculation"""
    
    def update_progress(step, message, progress, data=None):
        progress_data = {
            'step': step,
            'message': message,
            'progress': progress,
            'data': data or {},
            'timestamp': time.time()
        }
        redis_client.setex(
            f"progress:{task_id}", 
            3600,  # Expire after 1 hour
            json.dumps(progress_data)
        )
    
    try:
        # First update - almost instant
        update_progress(1, 'Initial processing complete', 10, 
                       {'initial_result': 'Quick calculation done'})
        
        # Simulate your heavy calculations
        calculations = [
            (2, 'Processing data chunk 1...', 30, {'chunk1': 'result1'}),
            (3, 'Processing data chunk 2...', 50, {'chunk2': 'result2'}),
            (4, 'Finalizing calculations...', 75, {'chunk3': 'result3'}),
            (5, 'Calculation complete!', 100, {'final': 'all_results'})
        ]
        
        for step, message, progress, data in calculations:
            # Your actual heavy calculation here
            time.sleep(30)  # Simulate processing time
            update_progress(step, message, progress, data)
            
    except Exception as exc:
        update_progress(-1, f'Error: {str(exc)}', -1, {'error': True})
        raise

@app.route('/start-calculation')
def start_calculation():
    """Start calculation and return task ID"""
    task = heavy_calculation_task.delay(task_id := f"task_{int(time.time())}")
    return jsonify({
        'status': 'started',
        'task_id': task_id,
        'celery_task_id': task.id
    })

@app.route('/stream-progress/<task_id>')
def stream_progress(task_id):
    """Stream progress updates"""
    
    def generate():
        last_step = 0
        
        while True:
            # Get progress from Redis
            progress_data = redis_client.get(f"progress:{task_id}")
            
            if progress_data:
                current_data = json.loads(progress_data)
                current_step = current_data['step']
                
                # Send update if there's new progress
                if current_step > last_step:
                    yield f"data: {json.dumps(current_data)}\n\n"
                    last_step = current_step
                    
                    # Break if complete or error
                    if current_data['progress'] >= 100 or current_data['progress'] == -1:
                        break
            
            time.sleep(1)  # Poll every second
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )

@app.route('/statistics')
def get_statistics():
    """get statistics for teams provided by arguments"""
    return jsonify({'message': 'Statistics endpoint placeholder. Not implemented yet.'})

@app.route('/')
def hello():
    return jsonify({'message': 'Hello, World!', 'version': __version__})

if __name__ == '__main__':
    app.run(debug=True)