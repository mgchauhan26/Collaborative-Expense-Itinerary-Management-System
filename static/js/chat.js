// Integrated Group Chat Client
document.addEventListener('DOMContentLoaded', () => {
  const chatEl = document.getElementById('chat');
  const groupId = chatEl.dataset.groupId;
  const currentUserId = parseInt(chatEl.dataset.currentUserId || '0', 10);
  const socket = io();
  const messagesEl = document.getElementById('messages');
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const fileInput = document.getElementById('chat-file');
  const emojiBtn = document.getElementById('emoji-btn');
  const emojiPickerContainer = document.getElementById('emoji-picker-container');
  const emojiPicker = emojiPickerContainer.querySelector('emoji-picker');
  const uploadBtn = document.getElementById('upload-btn');
  const statusBadge = document.getElementById('chat-status');

  function scrollToBottom(smooth = true) {
    messagesEl.scrollTo({
      top: messagesEl.scrollHeight,
      behavior: smooth ? 'smooth' : 'auto'
    });
  }

  function formatTime(isoString) {
    if (!isoString) return '';
    try {
      const date = new Date(isoString);
      if (isNaN(date.getTime())) return '';
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return '';
    }
  }

  function addMessage(data) {
    // Handle Status Messages (System messages)
    if (data.is_status || data.text?.includes('joined the') || data.text?.includes('left the')) {
      const li = document.createElement('li');
      li.className = 'chat-status';
      li.textContent = data.text || data.message;
      messagesEl.appendChild(li);
      scrollToBottom();
      return;
    }

    const li = document.createElement('li');
    const isMe = data.user_id === currentUserId;
    li.className = `chat-message ${isMe ? 'me' : 'them'}`;

    const time = formatTime(data.timestamp);

    // Message Bubble Structure
    let content = '';
    if (!isMe) {
      content += `<span class="meta">${data.user}</span>`;
    }

    content += `<div class="text">`;
    if (data.media_filename) {
      const url = `/static/uploads/${data.media_filename}`;
      content += `<img src="${url}" style="max-width:100%; border-radius:4px; margin-bottom:5px; display:block;"/>`;
    }
    if (data.text) {
      content += `<span>${data.text}</span>`;
    }
    content += `<span class="time">${time}</span>`;
    content += `</div>`;

    li.innerHTML = content;
    messagesEl.appendChild(li);
    scrollToBottom();
  }

  // Load History
  fetch(`/groups/${groupId}/messages`).then(r => r.json()).then(data => {
    if (data.error) {
      console.error('History fetch error:', data.error);
      return;
    }
    messagesEl.innerHTML = '';
    data.forEach(m => addMessage(m));
    setTimeout(() => scrollToBottom(false), 100);
  });

  socket.on('connect', () => {
    statusBadge.textContent = 'Connected';
    statusBadge.className = 'text-success';
    socket.emit('join', { group: groupId });
    setSendEnabled(true);
  });

  socket.on('disconnect', () => {
    statusBadge.textContent = 'Disconnected';
    statusBadge.className = 'text-danger';
    setSendEnabled(false);
  });

  // Real-time events
  socket.on('new_message', (data) => {
    addMessage(data);
  });

  function setSendEnabled(enabled) {
    const sendBtn = form.querySelector('button[type="submit"]');
    if (sendBtn) sendBtn.disabled = !enabled;
    input.disabled = !enabled;
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    socket.emit('message', { group: groupId, text });
    input.value = '';
    emojiPickerContainer.style.display = 'none';
  });

  // Emoji Picker Logic
  emojiBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isVisible = emojiPickerContainer.style.display === 'block';
    emojiPickerContainer.style.display = isVisible ? 'none' : 'block';
  });

  emojiPicker.addEventListener('emoji-click', event => {
    const emoji = event.detail.unicode;
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const text = input.value;
    input.value = text.substring(0, start) + emoji + text.substring(end);
    input.focus();
    input.selectionStart = input.selectionEnd = start + emoji.length;
  });

  // Close picker when clicking outside
  document.addEventListener('click', (e) => {
    if (!emojiPickerContainer.contains(e.target) && e.target !== emojiBtn) {
      emojiPickerContainer.style.display = 'none';
    }
  });

  // File upload
  uploadBtn.addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fetch(`/groups/${groupId}/upload`, { method: 'POST', body: fd }).then(r => r.json()).then(resp => {
      fileInput.value = null;
    });
  });
});
