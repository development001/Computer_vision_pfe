(function () {
  function init(options) {
    const {
      getSelectedDatasetId,
      api,
      notify,
      onSuccess,
    } = options;

    const uploadBtn = document.getElementById("upload-video-btn");
    const fileInput = document.getElementById("video-upload");
    const frameStepInput = document.getElementById("video-frame-step");
    const statusEl = document.getElementById("video-import-status");

    if (!uploadBtn || !fileInput || !frameStepInput || !statusEl) {
      return;
    }

    uploadBtn.addEventListener("click", async () => {
      const datasetId = getSelectedDatasetId();
      if (!datasetId) {
        notify("select a dataset first");
        return;
      }

      if (!fileInput.files || fileInput.files.length === 0) {
        notify("select a video first");
        return;
      }

      const everyNthFrame = parseInt(frameStepInput.value, 10);
      if (!Number.isInteger(everyNthFrame) || everyNthFrame < 1) {
        notify("every X frame must be an integer >= 1");
        return;
      }

      const form = new FormData();
      form.append("video", fileInput.files[0]);
      form.append("every_nth_frame", String(everyNthFrame));

      statusEl.textContent = "Extracting frames from video...";
      uploadBtn.disabled = true;

      try {
        const result = await api(`/training/datasets/${datasetId}/images/from-video`, {
          method: "POST",
          body: form,
        });

        fileInput.value = "";
        statusEl.textContent = `Extracted ${result.extracted_count} image(s) from ${result.video_name}.`;

        if (typeof onSuccess === "function") {
          await onSuccess();
        }
      } catch (e) {
        statusEl.textContent = "";
        notify(e.message);
      } finally {
        uploadBtn.disabled = false;
      }
    });
  }

  window.TrainingUploadVideo = { init };
})();
