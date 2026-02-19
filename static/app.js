const API_BASE = "";

const $ = (id) => document.getElementById(id);

let currentUser = null;
let loginStream = null;

/* OTP */
$("li_send_otp").onclick = async () => {
  const aad = $("li_aadhaar").value.trim();
  const phone = $("li_phone").value.trim();

  const res = await fetch("/api/send_otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aadhaar: aad, phone }),
  });

  if (!res.ok) return alert("OTP send failed");

  $("li_otp_section").style.display = "";
  $("li_verify_otp").style.display = "";
};

$("li_verify_otp").onclick = async () => {
  const aad = $("li_aadhaar").value.trim();
  const phone = $("li_phone").value.trim();
  const otp = $("li_otp").value.trim();

  const res = await fetch("/api/verify_otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aadhaar: aad, phone, otp }),
  });

  if (!res.ok) return alert("OTP invalid");

  $("li_face_section").style.display = "";
};

/* CAMERA */
$("li_start_cam").onclick = async () => {
  loginStream = await navigator.mediaDevices.getUserMedia({ video: true });
  $("li_video").srcObject = loginStream;
  $("li_capture").disabled = false;
};

$("li_capture").onclick = async () => {
  const video = $("li_video");
  const canvas = $("li_canvas");

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);

  const image = canvas.toDataURL("image/png");

  const res = await fetch("/api/login_face", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      aadhaar: $("li_aadhaar").value.trim(),
      phone: $("li_phone").value.trim(),
      image,
    }),
  });

  if (!res.ok) return alert("Face not matched");

  const data = await res.json();
  currentUser = data.user;

  loginStream.getTracks().forEach((t) => t.stop());

  $("authCard").style.display = "none";
  showDashboard();
};

async function showDashboard() {
  $("dashboard").style.display = "";
  $("userInfo").innerText =
    "Logged in: " + currentUser.name + " | Voter ID: " + currentUser.voterID;

  const res = await fetch("/api/list_parties");
  const data = await res.json();

  const container = $("candidates");
  container.innerHTML = "";

  data.parties.forEach((p) => {
    const div = document.createElement("div");
    div.className = "candidate";
    div.innerHTML = `
      <strong>${p.name}</strong>
      Candidate: ${p.candidate}
      <div>Votes: <span id="pc_${p.id}">${p.voteCount}</span></div>
      <button onclick="castVote('${p.id}')">Vote</button>
    `;
    container.appendChild(div);
  });
}

window.castVote = async function (party_id) {
  if (!confirm("Confirm vote?")) return;

  const res = await fetch("/api/vote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      aadhaar: currentUser.aadhaar,
      voterID: currentUser.voterID,
      party_id,
    }),
  });

  if (!res.ok) return alert("Vote failed");

  alert("Vote recorded");
};
