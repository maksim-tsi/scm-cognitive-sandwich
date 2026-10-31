// P8: same pinned b11815 parser/tokenizer; allow bounded alternating text-only history.
#include "server-common.h"
#include "chat.h"
#include "common.h"
#include "llama.h"
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>

int main(int argc, char ** argv) {
    try {
        if (argc != 2) throw std::runtime_error("expected metadata-only GGUF path");
        auto params = llama_model_default_params();
        params.vocab_only = true;
        params.n_gpu_layers = 0;
        std::unique_ptr<llama_model, decltype(&llama_model_free)> model(
            llama_model_load_from_file(argv[1], params), llama_model_free);
        if (!model) throw std::runtime_error("vocabulary load failed");
        const auto * vocab = llama_model_get_vocab(model.get());
        server_chat_params opt{};
        opt.use_jinja = true;
        opt.prefill_assistant = true;
        opt.reasoning_format = COMMON_REASONING_FORMAT_DEEPSEEK;
        opt.tmpls = common_chat_templates_init(model.get(), "");
        opt.allow_image = opt.allow_audio = opt.allow_video = false;
        opt.enable_thinking = true; // actual per-request false is parsed by OAI code
        opt.force_pure_content = false;
        const auto embedded = common_chat_templates_source(opt.tmpls.get());
        if (embedded.empty()) throw std::runtime_error("missing embedded template");
        std::string line;
        while (std::getline(std::cin, line)) {
            auto entry = json::parse(line);
            auto body = entry.at("body");
            const auto & messages = body.at("messages");
            if (!messages.is_array() || (messages.size() < 2 || messages.size() > 14 || messages.size() % 2 != 0) ||
                messages[0].at("role") != "system" || messages[1].at("role") != "user")
                throw std::runtime_error("bounded system/user/assistant text conversation required");
            for (size_t i = 2; i < messages.size(); ++i)
                if (messages[i].at("role") != (i % 2 == 0 ? "assistant" : "user"))
                    throw std::runtime_error("alternating text history required");
            for (const auto & msg : messages)
                if (!msg.at("content").is_string())
                    throw std::runtime_error("media or non-text input forbidden");
            if (body.at("chat_template_kwargs") != json({{"enable_thinking", false}}) ||
                body.at("tools") != json::array() || body.at("tool_choice") != "none" ||
                body.at("max_tokens") != 2048 || body.at("stream") != false ||
                body.at("response_format") != json({{"type", "json_object"}}))
                throw std::runtime_error("frozen request profile differs");
            for (const auto & forbidden : {"grammar", "json_schema", "reasoning_effort",
                 "reasoning_format", "continue_final_message", "add_generation_prompt", "echo"})
                if (body.contains(forbidden)) throw std::runtime_error("extra processing override forbidden");
            common_chat_session session;
            std::vector<raw_buffer> files;
            const auto parsed = oaicompat_chat_params_parse(vocab, body, opt, files, session);
            if (!files.empty()) throw std::runtime_error("media forbidden");
            // Same non-MTMD completion path: add_special=true, parse_special=true.
            const mtmd_helper_init_opt init_opt{};
            auto tokenized = tokenize_input_prompts(vocab, nullptr, parsed.at("prompt"), true, true, init_opt);
            if (tokenized.size() != 1 || tokenized[0].has_mtmd)
                throw std::runtime_error("unexpected tokenization shape");
            json result = {
                {"case_id", entry.at("case_id")}, {"rendered_prompt", parsed.at("prompt")},
                {"token_ids", tokenized[0].get_tokens()}, {"count", tokenized[0].size()},
                {"generation_prompt", session.generation_prompt()},
                {"template_source", embedded},
                {"vocab_add_bos", llama_vocab_get_add_bos(vocab)},
                {"vocab_add_eos", llama_vocab_get_add_eos(vocab)},
                {"bos_id", llama_vocab_bos(vocab)}, {"eos_id", llama_vocab_eos(vocab)},
                {"use_jinja", true}, {"enable_thinking", false},
                {"server_add_special", true}, {"server_parse_special", true},
                {"vocab_only", true}, {"llama_context_created", false}, {"generation_calls", 0}
            };
            std::cout << result.dump() << '\n';
        }
    } catch (const std::exception & e) {
        std::cerr << "P31 FAIL: " << e.what() << '\n';
        return 1;
    }
}
