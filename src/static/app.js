document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const loginForm = document.getElementById("login-form");
  const accountInfo = document.getElementById("account-info");
  const accountName = document.getElementById("account-name");
  const roleMessage = document.getElementById("role-message");
  const messageDiv = document.getElementById("message");
  let currentUser = null;

  function showMessage(element, text, isError = false) {
    element.textContent = text;
    element.className = isError ? "error" : "success";
    element.classList.remove("hidden");
  }

  async function responseData(response) {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "The request could not be completed");
    }
    return data;
  }

  function updateAccountUI() {
    const signedIn = currentUser !== null;
    loginForm.classList.toggle("hidden", signedIn);
    accountInfo.classList.toggle("hidden", !signedIn);
    signupForm.classList.toggle(
      "hidden",
      !signedIn || currentUser.role !== "student"
    );

    if (!signedIn) {
      accountName.textContent = "";
      roleMessage.textContent = "Sign in to manage activity signups.";
      return;
    }

    accountName.textContent = `Signed in as ${currentUser.username} (${currentUser.role})`;
    if (currentUser.role === "student") {
      roleMessage.textContent = "You can sign up for activities and remove your own signup.";
    } else if (currentUser.role === "staff" || currentUser.role === "admin") {
      roleMessage.textContent = "You can manage participant signups.";
    } else {
      roleMessage.textContent = "Parent accounts have read-only access.";
    }
  }

  async function fetchActivities() {
    try {
      const activities = await responseData(await fetch("/activities"));
      activitiesList.replaceChildren();
      activitySelect.replaceChildren(activitySelect.options[0]);

      Object.entries(activities).forEach(([name, details]) => {
        const activityCard = document.createElement("article");
        activityCard.className = "activity-card";

        const title = document.createElement("h4");
        title.textContent = name;
        activityCard.appendChild(title);

        for (const [label, value] of [
          ["", details.description],
          ["Schedule:", details.schedule],
          [
            "Availability:",
            `${details.max_participants - details.participants.length} spots left`,
          ],
        ]) {
          const paragraph = document.createElement("p");
          if (label) {
            const strong = document.createElement("strong");
            strong.textContent = `${label} `;
            paragraph.appendChild(strong);
          }
          paragraph.append(document.createTextNode(value));
          activityCard.appendChild(paragraph);
        }

        const participants = document.createElement("div");
        participants.className = "participants-container";
        const participantsTitle = document.createElement("h5");
        participantsTitle.textContent = "Participants:";
        participants.appendChild(participantsTitle);

        if (details.participants.length === 0) {
          const emptyMessage = document.createElement("p");
          emptyMessage.textContent = "No participants yet";
          participants.appendChild(emptyMessage);
        } else {
          const participantList = document.createElement("ul");
          participantList.className = "participants-list";
          details.participants.forEach((email) => {
            const item = document.createElement("li");
            const emailText = document.createElement("span");
            emailText.className = "participant-email";
            emailText.textContent = email;
            item.appendChild(emailText);

            const canUnregister =
              currentUser &&
              (currentUser.role === "staff" ||
                currentUser.role === "admin" ||
                (currentUser.role === "student" &&
                  currentUser.email.toLowerCase() === email.toLowerCase()));
            if (canUnregister) {
              const removeButton = document.createElement("button");
              removeButton.type = "button";
              removeButton.className = "delete-btn";
              removeButton.textContent = "Remove";
              removeButton.setAttribute("aria-label", `Remove ${email} from ${name}`);
              removeButton.addEventListener("click", () =>
                handleUnregister(name, email)
              );
              item.appendChild(removeButton);
            }
            participantList.appendChild(item);
          });
          participants.appendChild(participantList);
        }
        activityCard.appendChild(participants);
        activitiesList.appendChild(activityCard);

        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        activitySelect.appendChild(option);
      });
    } catch (error) {
      activitiesList.textContent = "Failed to load activities. Please try again later.";
      console.error("Error fetching activities:", error);
    }
  }

  async function handleUnregister(activity, email) {
    try {
      const query = currentUser.role === "student" ? "" : `?email=${encodeURIComponent(email)}`;
      const result = await responseData(
        await fetch(
          `/activities/${encodeURIComponent(activity)}/unregister${query}`,
          { method: "DELETE" }
        )
      );
      showMessage(messageDiv, result.message);
      await fetchActivities();
    } catch (error) {
      showMessage(messageDiv, error.message, true);
    }
  }

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(loginForm);
    try {
      currentUser = await responseData(
        await fetch("/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: formData.get("username"),
            password: formData.get("password"),
          }),
        })
      );
      loginForm.reset();
      document.getElementById("auth-message").textContent = "";
      updateAccountUI();
      await fetchActivities();
    } catch (error) {
      showMessage(document.getElementById("auth-message"), error.message, true);
    }
  });

  document.getElementById("logout-button").addEventListener("click", async () => {
    try {
      await responseData(await fetch("/auth/logout", { method: "POST" }));
      currentUser = null;
      updateAccountUI();
      await fetchActivities();
    } catch (error) {
      showMessage(document.getElementById("auth-message"), error.message, true);
    }
  });

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const activity = activitySelect.value;
      const result = await responseData(
        await fetch(`/activities/${encodeURIComponent(activity)}/signup`, {
          method: "POST",
        })
      );
      showMessage(messageDiv, result.message);
      signupForm.reset();
      await fetchActivities();
    } catch (error) {
      showMessage(messageDiv, error.message, true);
    }
  });

  async function loadCurrentUser() {
    try {
      const response = await fetch("/auth/me");
      if (response.ok) {
        currentUser = await response.json();
      } else if (response.status !== 401) {
        throw new Error("Unable to load account details");
      }
    } catch (error) {
      showMessage(document.getElementById("auth-message"), error.message, true);
    }
    updateAccountUI();
    await fetchActivities();
  }

  loadCurrentUser();
});
