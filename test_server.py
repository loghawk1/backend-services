import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("JSON2VIDEO_API_KEY")
BASE_URL = "https://api.json2video.com/v2/movies"


def create_video_with_captions(video_url: str) -> dict:
    """
    Create a new json2video job using the provided JSON structure.
    Returns the API response (which includes 'success' and 'project').
    """
    if not API_KEY:
        raise RuntimeError("JSON2VIDEO_API_KEY not found in environment")

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    # Payload uses the IDs you provided and moves elements INTO the scene.
    # We add fit:"cover" and explicit x,y,width,height to force full-canvas coverage.
    payload = {
        "id": "qbaasr7s",
        "resolution": "custom",
        "quality": "high",
        "scenes": [
            {
                "id": "qyjh9lwj",
                "comment": "Scene 1",
                "elements": [
                    {
                        "id": "q6dznzcv",
                        "type": "video",
                        "src": video_url,
                        "fit": "cover",
                        "position": "center",   # keep it centered while covering
                        # explicit bounds that match canvas (some APIs accept these)
                        "x": 0,
                        "y": 0,
                        "width": 768,
                        "height": 1344
                    },
                    {
                        "id": "q41n9kxp",
                        "type": "subtitles",
                        "settings": {
                            "style": "classic",
                            "font-family": "Nunito",
                            "font-size": 55,
                            "word-color": "#FFFFFF",
                            "line-color": "#FFFFFF",
                            "shadow-color": "#00000030",
                            "shadow-offset": 0,
                            "outline-width": 4,
                            "outline-color": "#00000020",
                            "max-words-per-line": 3,
                            "position": "custom",
                            "x": 384,
                            "y": 896
                        },
                        "language": "en"
                    }
                ]
            }
        ],
        "elements": [],   # keep top-level empty (we're using scene.elements)
        "width": 768,
        "height": 1344
    }

    resp = requests.post(BASE_URL, headers=headers, json=payload)
    # will raise HTTPError for 4xx/5xx
    resp.raise_for_status()
    return resp.json()


def check_video_status(project_id: str, interval: int = 8, timeout: int | None = None) -> dict:
    """
    Poll the API until the rendering job is done or error.
    Returns the 'movie' object on success.
    """
    if not API_KEY:
        raise RuntimeError("JSON2VIDEO_API_KEY not found in environment")

    headers = {"x-api-key": API_KEY}
    start = time.time()
    while True:
        resp = requests.get(f"{BASE_URL}?project={project_id}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        movie = data.get("movie", {})
        status = movie.get("status")
        msg = movie.get("message", "")
        print(f"[{status}] {msg}")

        if status == "done":
            return movie
        if status == "error":
            raise RuntimeError(f"Render error: {movie.get('message')}")
        if timeout and (time.time() - start) > timeout:
            raise TimeoutError("Timed out waiting for render")

        time.sleep(interval)


# helper wrapper (optional)
def create_and_wait(video_url: str, poll_interval: int = 8, timeout: int | None = None) -> dict:
    """
    Convenience wrapper: create job and wait until completion, returning movie dict.
    """
    create_resp = create_video_with_captions(video_url)
    if not create_resp.get("success"):
        raise RuntimeError(f"Create failed: {create_resp}")
    project_id = create_resp.get("project")
    print("Project created:", project_id)
    return check_video_status(project_id, interval=poll_interval, timeout=timeout)


if __name__ == "__main__":
    # Example usage
    test_video = "https://v3.fal.media/files/penguin/nnFK0rn607RdM_S439Ox9_output.mp4"
    print("creating job...")
    create_response = create_video_with_captions(test_video)
    print("create response:", create_response)

    pid = create_response.get("project")
    if pid:
        print("polling for result...")
        movie = check_video_status(pid)
        print("final movie:", movie)
        print("download url:", movie.get("url"))
