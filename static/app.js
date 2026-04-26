// ---------------- NAVIGATION ----------------
function goToRegister() {
  document.getElementById("page_register").style.display = "block";
  document.getElementById("page_login").style.display = "none";
  document.getElementById("page_vote").style.display = "none";
  document.getElementById("page_results").style.display = "none";
}

function goToLogin() {
  document.getElementById("page_register").style.display = "none";
  document.getElementById("page_login").style.display = "block";
  document.getElementById("page_vote").style.display = "none";
  document.getElementById("page_results").style.display = "none";
}

function goToVote() {
  document.getElementById("page_register").style.display = "none";
  document.getElementById("page_login").style.display = "none";
  document.getElementById("page_vote").style.display = "block";
  document.getElementById("page_results").style.display = "none";
}

function goToResults() {
  document.getElementById("page_register").style.display = "none";
  document.getElementById("page_login").style.display = "none";
  document.getElementById("page_vote").style.display = "none";
  document.getElementById("page_results").style.display = "block";

  loadResults();

  // auto refresh every 2 sec
  setInterval(loadResults, 2000);
}

// ---------------- CAMERA ----------------
async function startCamera(videoId) {
  const video = document.getElementById(videoId);
  const stream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = stream;
}

// ---------------- REGISTER ----------------
document.getElementById("reg_start_camera").onclick = () => {
  startCamera("reg_video");
};

document.getElementById("reg_submit").onclick = async () => {
  const aadhaar = document.getElementById("reg_aadhaar").value;
  const video = document.getElementById("reg_video");

  if (!aadhaar) {
    alert("Enter Aadhaar");
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 240;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, 320, 240);

  const image = canvas.toDataURL("image/jpeg");

  const res = await fetch("/api/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aadhaar, image }),
  });

  const data = await res.json();

  if (data.message) {
    alert("Registered successfully");
    goToLogin();
  } else {
    alert(data.error);
  }
};

// ---------------- OTP ----------------
document.getElementById("login_send_otp").onclick = async () => {
  const aadhaar = document.getElementById("login_aadhaar").value;

  if (!aadhaar) {
    alert("Enter Aadhaar");
    return;
  }

  await fetch("/api/send_otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aadhaar }),
  });

  alert("OTP is 123456");

  document.getElementById("otp_section").style.display = "block";
};

document.getElementById("login_verify_otp").onclick = async () => {
  const aadhaar = document.getElementById("login_aadhaar").value;
  const otp = document.getElementById("login_otp").value;

  const res = await fetch("/api/verify_otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aadhaar, otp }),
  });

  const data = await res.json();

  if (data.message) {
    alert("OTP verified");
    document.getElementById("face_section").style.display = "block";
  } else {
    alert(data.error);
  }
};

// ---------------- LOGIN ----------------
document.getElementById("login_start_camera").onclick = () => {
  startCamera("login_video");
};

document.getElementById("login_submit").onclick = async () => {
  const aadhaar = document.getElementById("login_aadhaar").value;
  const video = document.getElementById("login_video");

  if (!aadhaar) {
    alert("Enter Aadhaar");
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 240;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, 320, 240);

  const image = canvas.toDataURL("image/jpeg");

  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aadhaar, image }),
  });

  const data = await res.json();

  if (data.success) {
    alert("Login successful");
    goToVote();
    loadParties(aadhaar);
  } else {
    alert(data.error || "Login failed");
  }
};

// ---------------- LOAD PARTIES ----------------
async function loadParties(aadhaar) {
  const res = await fetch("/api/parties");
  const parties = await res.json();

  const container = document.getElementById("party_list");
  container.innerHTML = "";

  parties.forEach((p) => {
    const div = document.createElement("div");

    div.innerHTML = `
      <h3>${p.name}</h3>
      <p>Votes: ${p.voteCount}</p>
      <button onclick="vote('${aadhaar}', '${p.id}')">Vote</button>
      <hr>
    `;

    container.appendChild(div);
  });
}

// ---------------- VOTE ----------------
async function vote(aadhaar, party_id) {
  const res = await fetch("/api/vote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aadhaar, party_id }),
  });

  const data = await res.json();

  if (data.message) {
    alert("Thanks for voting");

    goToResults(); // 🔥 go to live results
  } else {
    alert(data.error);
  }
}

// ---------------- RESULTS ----------------
async function loadResults() {
  const res = await fetch("/api/parties");
  const parties = await res.json();

  const container = document.getElementById("results_list");
  container.innerHTML = "";

  parties.forEach((p) => {
    const div = document.createElement("div");

    div.innerHTML = `
      <h3>${p.name}</h3>
      <p>Votes: ${p.voteCount}</p>
      <hr>
    `;

    container.appendChild(div);
  });
}
