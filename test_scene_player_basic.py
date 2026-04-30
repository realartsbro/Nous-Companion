import asyncio
import sys
sys.path.insert(0, "src")
from server.scene_player import ScenePlayer

async def main():
    player = ScenePlayer()
    
    # Test loading a real scene file
    status = await player.load_scene("demo-scenes/variant-a-witness.nous-scene.json")
    print("Load status:", status)
    
    assert status["status"] == "ready"
    assert status["total_scenes"] == 3
    assert status["meta"]["title"] == "Demo: The Witness"
    
    # Test play / pause / stop lifecycle (headless, no server)
    player.play()
    assert player.get_status()["status"] == "playing"
    
    await asyncio.sleep(0.1)
    player.pause()
    assert player.get_status()["status"] == "paused"
    
    await asyncio.sleep(0.1)
    player.play()  # resume
    assert player.get_status()["status"] == "playing"
    
    player.stop()
    assert player.get_status()["status"] == "ready"
    assert player.get_status()["current_index"] == 0
    
    print("All basic tests passed!")

if __name__ == "__main__":
    asyncio.run(main())
