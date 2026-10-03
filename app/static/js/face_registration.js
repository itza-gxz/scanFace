const video = document.getElementById("video"), overlay = document.getElementById("overlay");
const msg = document.getElementById("msg"), prog = document.getElementById("prog");
const cam = new Camera(video), TARGET = 8;
let lastOk = false, capturing = false, samples = [];

function say(text, kind) { msg.className = "alert mt-3 mb-2 alert-" + kind; msg.textContent = text; }

async function detectLoop() {
  if (!cam.running) return;
  try {
    const res = await postJSON("/api/face/detect", {image: cam.capture()});
    lastOk = res.ok;
    drawBox(overlay, video, res, res.ok ? "#28a745" : "#dc3545");
    say(res.message, res.ok ? "success" : "warning");
  } catch (e) { lastOk = false; say(e.message, "danger"); }
  setTimeout(detectLoop, 700);
}

document.getElementById("startBtn").onclick = async () => {
  try { await cam.start(); document.getElementById("captureBtn").disabled = false; detectLoop(); }
  catch (e) { say(e.message, "danger"); toast(e.message, "danger"); }
};

document.getElementById("captureBtn").onclick = () => {
  if (capturing) return;
  capturing = true; samples = [];
  const timer = setInterval(async () => {
    if (lastOk) { samples.push(cam.capture()); }
    prog.style.width = (samples.length / TARGET * 100) + "%"; prog.textContent = samples.length + "/" + TARGET;
    if (samples.length >= TARGET) {
      clearInterval(timer);
      try {
        const r = await postJSON("/api/face/register", {student_id: +document.getElementById("student").value, images: samples});
        say(r.message + " (" + r.samples + " samples)", "success"); toast(r.message, "success");
        setTimeout(() => location.reload(), 1500);
      } catch (e) { say(e.message, "danger"); toast(e.message, "danger"); }
      capturing = false;
    }
  }, 600);
};

document.getElementById("toggleBtn").onclick = async () => {
  try { const r = await postJSON("/api/face/" + document.getElementById("student").value + "/toggle"); toast("Face status: " + r.status, "success"); setTimeout(() => location.reload(), 800); }
  catch (e) { toast(e.message, "danger"); }
};
document.getElementById("deleteBtn").onclick = async () => {
  if (!confirm("Delete this student's face data?")) return;
  try { await postJSON("/api/face/" + document.getElementById("student").value, null, "DELETE"); toast("Face data deleted.", "success"); setTimeout(() => location.reload(), 800); }
  catch (e) { toast(e.message, "danger"); }
};
