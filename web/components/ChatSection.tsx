'use client'

import { useEffect, useRef, useState } from 'react'
import api from '@/utils/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChatMessage, ChatSectionProps } from '@/utils/schemes'
import { useLanguage } from '@/utils/LanguageContext'

export default function ChatSection({
  projectName,
  activeTab,
  setActiveTab,
  chatMessages,
  setChatMessages,
  userInput,
  setUserInput,
  hasProjectResults,
  handleClearChatHistory,
  calculationResult
}: ChatSectionProps) {
  const { t } = useLanguage()
  const chatContainerRef = useRef<HTMLDivElement>(null)
  const [isSending, setIsSending] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)

  // 自动滚动到底部
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [chatMessages])

  // ✅ 进入某个项目时，从后端加载该项目的历史聊天
  useEffect(() => {
    if (!projectName) return

    const fetchHistory = async () => {
      try {
        const res = await api.chat.getHistory(projectName)
        if (res?.data?.history) {
          const history = res.data.history as { role: 'user' | 'assistant'; content: string }[]
          setChatMessages(
            history.map((msg) => ({
              role: msg.role,
              content: msg.content,
              // 后端没给时间，就先用当前时间占位；如果你将来加 timestamp 字段，这里可以改成 new Date(msg.timestamp)
              timestamp: new Date(),
            }))
          )
        }
      } catch (error) {
        console.error('Failed to load chat history:', error)
      }
    }

    fetchHistory()
  }, [projectName, setChatMessages])

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

  // ------------------------------------------------------
  // 🚀 核心：SSE + 模拟 ChatGPT 打字流式
  // ------------------------------------------------------
  const handleSendMessage = async () => {
    if (!userInput.trim() || isSending) return
    if (!projectName || !hasProjectResults) return

    const userMsg: ChatMessage = {
      role: 'user',
      content: userInput,
      timestamp: new Date(),
    }

    const baseIndex = chatMessages.length

    // 先插入用户消息 + 一个空的 assistant 消息
    setChatMessages((prev) => [
      ...prev,
      userMsg,
      {
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      },
    ])

    setUserInput('')
    setIsSending(true)
    setIsStreaming(true)

    try {
      const response = await fetch(api.chat.stream(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: projectName,
          messages: [...chatMessages, userMsg].map((m) => ({
            role: m.role,
            content: m.content,
          })),
          config: null,
        }),
      })

      if (!response.body) throw new Error('ReadableStream not supported')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      let buffer = ''
      let currentType: 'output' | 'action' | 'observation' | null = null
      let currentData = ''
      let accumulatedText = ''

      const updateAssistant = (text: string) => {
        setChatMessages((prev) => {
          const updated = [...prev]
          const assistantIndex = baseIndex + 1
          if (!updated[assistantIndex]) return prev
          updated[assistantIndex] = {
            ...updated[assistantIndex],
            content: text,
          }
          return updated
        })
      }

      const flushCurrentEvent = async () => {
        if (!currentType || !currentData) return

        if (currentType === 'output') {
          const tokens = currentData.split(/(\s+)/).filter(Boolean)
          for (const token of tokens) {
            accumulatedText += token
            updateAssistant(accumulatedText)
            await sleep(12) // 控制“打字”速度
          }
        }

        currentType = null
        currentData = ''
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('data:')) {
            await flushCurrentEvent()

            let dataLine = line.slice(5)
            if (dataLine.startsWith(' ')) dataLine = dataLine.slice(1)
            if (!dataLine) continue

            if (dataLine === '[DONE]') {
              await flushCurrentEvent()
              setIsStreaming(false)
              setIsSending(false)
              return
            }

            if (dataLine.startsWith('Action:')) {
              currentType = 'action'
              currentData = dataLine
              continue
            }

            if (dataLine.startsWith('Observation:')) {
              currentType = 'observation'
              currentData = dataLine
              continue
            }

            currentType = 'output'
            currentData = dataLine
          } else {
            if (currentType) {
              currentData += '\n' + line
            }
          }
        }
      }

      await flushCurrentEvent()
    } catch (err) {
      console.error('Send error:', err)
    } finally {
      setIsSending(false)
      setIsStreaming(false)
    }
  }

  // ------------------------------------------------------
  // 🎨 UI：保持你之前那套设计 + Markdown
  // ------------------------------------------------------
  return (
    <div className="bg-white/90 backdrop-blur-xl border border-gray-100 shadow-xl rounded-2xl p-8 max-w-screen-xl w-full">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-2">
            {t('chatAboutProject')}
          </h2>

          {projectName && (
            <div className="flex flex-wrap items-center gap-3 text-sm">

              {/* Project name badge */}
              <span className="px-3 py-1 bg-green-100 text-green-700 rounded-lg flex items-center gap-1">
                <span>🏗</span>
                <span className="font-medium">Project:</span>
                <span className="font-semibold">{projectName}</span>
              </span>

              {/* Total emissions */}
              {calculationResult?.summary_emission?.project_total_emission_tco2 && (
                <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-lg flex items-center gap-1">
                  <span>🌍</span>
                  <span className="font-medium">Emissions:</span>
                  <span className="font-semibold">
                    {calculationResult.summary_emission.project_total_emission_tco2.toFixed(2)} tCO₂
                  </span>
                </span>
              )}

              {/* Calculation timestamp */}
              {calculationResult?.summary_emission?.calculation_time && (
                <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded-lg flex items-center gap-1">
                  <span>⏱</span>
                  <span className="font-medium">Calculated:</span>
                  <span className="font-semibold">
                    {new Date(calculationResult.summary_emission.calculation_time * 1000)
                      .toLocaleString([], { month: "short", day: "numeric", year: "numeric" })}
                  </span>
                </span>
              )}

            </div>
          )}
        </div>



        {chatMessages.length > 0 && (
          <button
            onClick={handleClearChatHistory}
            className="px-3 py-1.5 text-sm rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 transition"
          >
            {t('clearChat')}
          </button>
        )}
      </div>

      {/* Empty states */}
      {!projectName ? (
        <div className="text-center py-16">
          <p className="text-gray-500 mb-4">
            {t('uploadProjectToStartChat')}
          </p>
          <button
            onClick={() => setActiveTab('upload')}
            className="px-6 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
          >
            {t('uploadProject')}
          </button>
        </div>
      ) : !hasProjectResults ? (
        <div className="text-center py-16">
          <p className="text-gray-500 mb-4">
            {t('runCalculationToEnableChat')}
          </p>
          <button
            onClick={() => setActiveTab('results')}
            className="px-6 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
          >
            {t('viewResults')}
          </button>
        </div>
      ) : (
        <>
          {/* Messages */}
          <div
            ref={chatContainerRef}
            className="h-[520px] overflow-y-auto pr-2 space-y-4 mb-6"
          >
            {chatMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <p>{t('askAboutCarbonEmissions')}</p>
                <ul className="mt-4 text-left space-y-1 text-gray-600">
                  <li>{t('whichItemsEmitMostCarbon')}</li>
                  <li>{t('showEmissionBreakdown')}</li>
                  <li>{t('howToReduceEmissions')}</li>
                </ul>
           

              </div>
            ) : (
              chatMessages.map((msg, i) => {
                const isUser = msg.role === 'user'
                const isLastAssistant =
                  msg.role === 'assistant' && i === chatMessages.length - 1

                return (
                  <div
                    key={i}
                    className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div className="w-8 h-8 rounded-full bg-green-200 flex items-center justify-center mr-3 flex-shrink-0">
                        <span className="text-green-700 text-xs font-semibold">
                          K
                        </span>
                      </div>
                    )}

                    <div
                      className={`
                        max-w-[90%] px-4 py-3 rounded-2xl shadow-sm 
                        text-sm
                        ${
                          isUser
                            ? 'bg-gradient-to-r from-green-400 to-blue-500 text-white'
                            : 'bg-gray-100 text-gray-800'
                        }
                      `}
                    >
                      <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0 prose-strong:font-semibold prose-code:text-[0.85em] prose-code:bg-black/5 prose-code:px-1 prose-code:py-[1px] prose-code:rounded">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>

                      {isLastAssistant && isStreaming && (
                        <span className="inline-block animate-pulse ml-1 text-gray-400">
                          ▍
                        </span>
                      )}

                      <div
                        className={`text-xs mt-1 ${
                          isUser ? 'text-blue-100/80' : 'text-gray-400'
                        }`}
                      >
                        {msg.timestamp.toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                    </div>

                    {isUser && (
                      <div className="w-8 h-8 rounded-full bg-blue-200 flex items-center justify-center ml-3 flex-shrink-0">
                        <span className="text-blue-700 text-xs font-semibold">
                          You
                        </span>
                      </div>
                    )}
                  </div>
                )
              })
            )}

            {isStreaming && (
              <div className="flex items-center space-x-2 text-gray-400 text-xs mt-2">
                <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" />
                <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce delay-150" />
                <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce delay-300" />
                <span>{t('assistantThinking')}</span>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="flex items-center bg-gray-100 rounded-xl p-2 border border-gray-300">
            <input
              className="flex-1 bg-transparent px-3 py-2 outline-none text-gray-700"
              placeholder={t('askAboutCarbon')}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !isSending && handleSendMessage()}
            />
            <button
              onClick={handleSendMessage}
              disabled={isSending || !userInput.trim()}
              className={`px-5 py-2 rounded-lg text-sm font-medium text-white transition ${
                isSending || !userInput.trim()
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-green-600 hover:bg-green-700'
              }`}
            >
              {isSending ? t('sending') : t('send')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
