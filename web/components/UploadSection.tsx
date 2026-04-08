'use client'

import { useState, useRef } from 'react'
import { useLanguage } from '../utils/LanguageContext'

interface UploadSectionProps {
  onFileUpload: (formData: FormData, onComplete?: (result: any) => void) => void;
  isLoading: boolean;
  progress: {
    percentage: number;
    status: string;      // data.message
    stepText?: string;   // Step 1 / Step 2 / Step 3
    itemName?: string;   // Sub-item name (optional)
  };
}

export default function UploadSection({
  onFileUpload,
  isLoading,
  progress,
}: UploadSectionProps) {
  const { t } = useLanguage()
  const [file, setFile] = useState<File | null>(null)
  const [projectName, setProjectName] = useState('')
  const [isDragActive, setIsDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
    }
  }

  const triggerFileInput = () => {
    fileInputRef.current?.click()
  }

  // Handle drag events
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  }

  // Handle drop event
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  }

  const removeFile = () => {
    setFile(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return

    const formData = new FormData()
    formData.append('file', file)

    // Ensure project_name is ALWAYS sent (backend requires it)
    const finalProjectName =
      projectName.trim() || file.name.replace(/\.[^/.]+$/, '') || 'kcec-project'

    formData.append('project_name', finalProjectName)
    if (!projectName.trim()) {
      // sync back to input so user sees the auto name
      setProjectName(finalProjectName)
    }

    // Delegate to parent: parent will call /upload-project + /calculate-emission + SSE
    onFileUpload(formData);
  }

  return (
    <div className="bg-white rounded-2xl shadow-xl p-6">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-gray-800 mb-2">
          {t('carbonEmissionAnalysis')}
        </h2>
        <p className="text-gray-600">
          {t('uploadYourFile')}
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="space-y-6">
          {/* File Upload Area */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('projectFile')}
            </label>

            <div
              className={`mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
                isDragActive
                  ? "border-blue-500 bg-blue-50"
                  : file
                  ? "border-green-300 bg-green-50"
                  : "border-gray-300 hover:border-blue-400 hover:bg-blue-50"
              }`}
              onClick={triggerFileInput}
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
            >
              <div className="space-y-1 text-center">
                {/* File Icon */}
                {file ? (
                  <div className="flex items-center justify-center text-green-600">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-8 w-8"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                  </div>
                ) : (
                  <div className="flex items-center justify-center text-gray-600">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-8 w-8"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                      />
                    </svg>
                  </div>
                )}

                {/* Upload text */}
                <div className="flex text-sm text-gray-600">
                  <span className="relative font-medium text-blue-600 hover:text-blue-500">
                    {t('uploadFile')}
                  </span>
                  <p className="pl-1">{t('orDragAndDrop')}</p>
                </div>

                <p className="text-xs text-gray-500">
                  {t('supportedFormats')}
                </p>

                {file && (
                  <p className="text-sm font-medium text-green-600 mt-2">
                    {file.name}
                  </p>
                )}
              </div>

              <input
                ref={fileInputRef}
                type="file"
                className="sr-only"
                onChange={handleFileChange}
                accept=".json,.csv,.xlsx,.xls"
              />
            </div>

            {file && (
              <div className="mt-2 flex justify-center">
                <button
                  type="button"
                  onClick={removeFile}
                  className="text-sm font-medium text-red-600 hover:text-red-500"
                >
                  {t('removeFile')}
                </button>
              </div>
            )}
          </div>

          {/* Project Name Input */}
          <div>
            <label
              htmlFor="project-name"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              {t('projectName')}
            </label>
            <input
              type="text"
              id="project-name"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-3 border"
              placeholder={t('enterProjectName')}
            />
          </div>

          {/* Submit Button */}
          <div>
            <button
              type="submit"
              disabled={!file || isLoading}
              className={`w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                !file || isLoading
                  ? "bg-gray-400 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700 focus:ring-blue-500"
              }`}
            >
              {isLoading ? t('processing') : t('startAnalysis')}
            </button>
          </div>
        </div>
      </form>

      {/* --- Clean Modern Progress Bar (only one!) --- */}
      {isLoading && (
        <div className="mt-6">
          {/* Status Text */}
          <div className="text-sm text-gray-700 font-medium mb-1">
            {progress.status}
          </div>

          {/* Step Text (optional) */}
          {progress.stepText && (
            <div className="text-xs text-gray-600 mb-1">{progress.stepText}</div>
          )}

          {/* Sub-item name (optional) */}
          {progress.itemName && (
            <div className="text-xs text-gray-500 mb-1">
              Processing: {progress.itemName}
            </div>
          )}

          {/* Percentage */}
          <div className="flex justify-between text-sm text-gray-600 mb-1">
            <span>{progress.percentage}%</span>
          </div>

          {/* Progress Bar */}
          <div className="overflow-hidden h-2 bg-gray-200 rounded-full">
            <div
              className="h-full bg-blue-600 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress.percentage}%` }}
            ></div>
          </div>
        </div>
      )}
    </div>
  );

}