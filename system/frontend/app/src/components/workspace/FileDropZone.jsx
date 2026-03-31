import React, { useCallback, useState } from "react";

export default function FileDropZone({ onFileDrop, children }) {
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = React.useRef(0);

  const handleDragEnter = useCallback((e) => {
    e.preventDefault();
    dragCounter.current++;
    if (e.dataTransfer.types.includes("Files")) setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current === 0) setIsDragging(false);
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    dragCounter.current = 0;
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0 && onFileDrop) {
      onFileDrop(e.dataTransfer.files);
    }
  }, [onFileDrop]);

  return (
    <div
      className="file-drop-wrapper"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {children}
      {isDragging && (
        <div className="file-drop-zone is-active">
          <div className="file-drop-zone-text">Drop files here</div>
        </div>
      )}
    </div>
  );
}
