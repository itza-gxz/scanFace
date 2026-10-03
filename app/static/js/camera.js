function toast(msg, kind) {
  const box = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = "alert alert-" + (kind || "info") + " shadow-sm";
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

async function postJSON(url, body, method) {
  const r = await fetch(url, {method: method || "POST", headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (r.status === 401) { window.location = "/login"; }
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed (" + r.status + ").");
  return data;
}
function getJSON(url) { return fetch(url).then(async r => { if (!r.ok) throw new Error("Request failed (" + r.status + ")."); return r.json(); }); }

class Camera {
  constructor(video) { this.video = video; this.stream = null; }
  static explain(e) {
    switch (e.name) {
      case "NotAllowedError": return "Camera permission denied. Allow camera access in the browser address bar and try again.";
      case "NotFoundError": return "No camera device found.";
      case "NotReadableError": return "The camera is in use by another application.";
      default: return "Could not start the camera: " + e.message;
    }
  }
  async start() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Camera API unavailable. Open the app at http://127.0.0.1:8000 or over HTTPS in a modern browser.");
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: "user", width: {ideal: 640}, height: {ideal: 480}}, audio: false});
    } catch (e) { throw new Error(Camera.explain(e)); }
    this.video.srcObject = this.stream;
    this.stream.getVideoTracks()[0].addEventListener("ended", () => toast("Camera stopped.", "warning"));
    await this.video.play();
  }
  stop() { if (this.stream) this.stream.getTracks().forEach(t => t.stop()); this.stream = null; this.video.srcObject = null; }
  get running() { return !!this.stream; }
  capture() {
    const c = document.createElement("canvas");
    c.width = this.video.videoWidth; c.height = this.video.videoHeight;
    c.getContext("2d").drawImage(this.video, 0, 0);
    return c.toDataURL("image/jpeg", 0.9);
  }
}

function drawBox(canvas, video, res, color) {
  canvas.width = video.videoWidth || 640; canvas.height = video.videoHeight || 480;
  const g = canvas.getContext("2d"); g.clearRect(0, 0, canvas.width, canvas.height);
  const boxes = res.faces || (res.box ? [res.box] : []);
  g.lineWidth = 3; g.strokeStyle = color;
  boxes.forEach(b => g.strokeRect(b[0], b[1], b[2], b[3]));
}
