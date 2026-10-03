const video = document.getElementById("video"), overlay = document.getElementById("overlay");
const msg = document.getElementById("msg"), cam = new Camera(video);
let busy = false, pausedUntil = 0, pos = {lat: null, lon: null};
const $ = id => document.getElementById(id);

setInterval(() => { const n = new Date(); $("d").textContent = n.toLocaleDateString(); $("t").textContent = n.toLocaleTimeString(); }, 1000);
if (navigator.geolocation) navigator.geolocation.getCurrentPosition(p => { pos = {lat: p.coords.latitude, lon: p.coords.longitude}; }, () => {});

function say(text, kind) { msg.className = "alert alert-" + kind; msg.textContent = text; }
function reset() { ["r_name", "r_code", "r_rec", "r_score", "r_status", "r_in", "r_out"].forEach(i => $(i).textContent = "-"); }

async function loop() {
  if (!cam.running) return;
  if (!busy && Date.now() > pausedUntil) {
    busy = true;
    try {
      const r = await postJSON("/api/face/recognize", {image: cam.capture(), session_id: +$("session").value, action: $("action").value, latitude: pos.lat, longitude: pos.lon});
      drawBox(overlay, video, r, r.recognized ? "#28a745" : "#dc3545");
      if (r.recognized) {
        $("r_name").textContent = r.student.name; $("r_code").textContent = r.student.code;
        $("r_rec").textContent = "Recognized"; $("r_score").textContent = r.score;
        $("r_status").textContent = r.status || "-"; $("r_in").textContent = r.check_in || "-"; $("r_out").textContent = r.check_out || "-";
        say(r.message, r.created ? "success" : "warning");
        pausedUntil = Date.now() + 4000;
      } else {
        reset(); if (r.score !== undefined) $("r_score").textContent = r.score;
        $("r_rec").textContent = r.code === "unknown" ? "Unknown person" : "Not recognized";
        say(r.message, "warning");
      }
    } catch (e) { say(e.message, "danger"); }
    busy = false;
  }
  setTimeout(loop, 1200);
}

$("startBtn").onclick = async () => { try { await cam.start(); say("Camera started.", "info"); loop(); } catch (e) { say(e.message, "danger"); toast(e.message, "danger"); } };
$("stopBtn").onclick = () => { cam.stop(); say("Camera stopped.", "secondary"); };
