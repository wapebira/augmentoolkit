import re

# from .multi_turn_conversation_grammar import multi_turn_conversation_grammar
from .constants import LOGICAL_MODEL, INPUT_DIRECTORY
from .format_qatuples import format_qatuples
from .extract_name import extract_name
import random
import os
import traceback
import json
import logging


# all characters in this prompt are over 18

# Explanation of wtf the first few-shot example is:
# No I do not have a teacher-student fetish, the reason why Elise is a teacher is an adaptation to the following three facts:
# 1. This tool is meant to be able to generate data for training ERP bots by default
# 2. This tool is also meant to be able to take in educational material by default
# 3. When generating characters that would know about educational material, the model tends to generate academics or professors in that field, talking to students.
# Given these facts, we clearly need to prompt the model to be able to generate horny teachers, or else it's going to just do it poorly when it realizes it has a sexualized character that's also a teacher. I didn't want to choose this, the constraints of the problem forced me to.


def extract_steps(text, steps=[2, 4, 5]):
    """
    Extracts the specified steps from the text.

    Args:
    text (str): The input text containing various steps.
    steps (list of int): The step numbers to extract.

    Returns:
    str: A new string with each specified step's content on its own line.
    """
    step_pattern = "|".join([f"Step {step}\." for step in steps])
    matches = re.findall(
        f"({step_pattern})\s*(.*?)\s*(?=(Step \d\.|$))", text, re.DOTALL
    )

    # Extract and join the matched content, skipping the "Step n." part
    extracted_text = "\n".join(match[1].strip() for match in matches)
    return extracted_text


def extract_first_words(character_name, text):
    # Regular expression pattern to extract first word after the character's name
    pattern = rf"{character_name}: \"(\w+)"

    # Find all matches in the text
    matches = re.findall(pattern, text)

    return matches


class GenerationStep:
    def __init__(self,
                 prompt_path="", # relative to the Inputs directory
                 regex=re.compile(r'.*', re.DOTALL), # take whole completion
                 sampling_params={
                     "temperature": 1,
                     "top_p": 1,
                     "max_tokens": 3000,
                     "stop": [
                            "### Response",
                            "\n\n\n\n\n",
                            "</s>",
                            "# Input:",
                            "[INST]",
                            "### Instruction",
                            "### Information",
                            "## Information",
                            "## Instruction",
                            "Name:",
                        ]
                    },
                 completion_mode=True, # Chat vs completion mode
                 retries=0,
                 engine_wrapper=None,
                 arguments={}, # arguments is a dict of things where the keys are the strings in the prompt that the thing should replace (minus curly brackets), and the values are what they get replaced with
                 log_level=logging.INFO  # Default logging level
                ):
        self.prompt_path = prompt_path
        self.regex = regex
        self.sampling_params = sampling_params
        self.completion_mode = completion_mode
        self.retries = retries
        self.arguments = arguments
        self.log_level = log_level
        if not engine_wrapper:
            raise Exception("Engine wrapper not passed in!")
        self.engine_wrapper = engine_wrapper
        logging.basicConfig(level=self.log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    
    async def generate(self):
        # Current file directory
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Dynamic INPUT_DIRECTORY path
        full_prompt_path = os.path.join(current_dir, '..', '..', 'inputs',self.prompt_path)
        # Read file and substitute thing with arguments as needed
        with open(full_prompt_path, 'r') as pf:
            prompt = pf.read()
            prompt_formatted = prompt.format(**self.arguments)
        logging.info(f"Formatted prompt for generation: {prompt_formatted}")
        if self.completion_mode:
            times_tried = 0
            while times_tried <= self.retries:
                try:
                    response = await self.engine_wrapper.submit_completion(prompt_formatted, self.sampling_params)
                    filtered_response = re.search(self.regex, response).group(1)
                    return filtered_response
                except Exception as e:
                    logging.error(f"Error in Generation Step: {e}")
                    traceback.print_exc()
                    times_tried += 1
            raise Exception("Generation step failed -- too many retries!")
        else:
            messages = json.loads(prompt_formatted)
            while times_tried <= self.retries:
                try:
                    response = await self.engine_wrapper.submit_chat(messages, self.sampling_params)
                    filtered_response = re.search(self.regex, response).group(1)
                    return filtered_response
                except Exception as e:
                    logging.error(f"Error in Generation Step: {e}")
                    traceback.print_exc()
                    times_tried += 1
            raise Exception("Generation step failed -- too many retries!")






async def multi_turn_conversation(
    qatuples, character, scenario, scenario_plan, engine_wrapper, assistant_mode=False # assistant mode is handled by changing the prompt paths in the control flow code
):
    """
    Produce a plan for a character card for an RP character that's going to answer one of the questions generated from the text. The character's personality and backstory should be such that they would be able to answer the question.

    Format: Question: [question]\n\n
    """

    charname = extract_name(character)
    first_words_of_card = extract_first_words(charname, character)
    conv_starters = [  # prevents it from regurgitating the card (when combined with filtering)
        "Ah",
        "Oh",
        # "You",
        # "Really",
        "I",
        # "What",
        # "So",
        "Welcome",
        "Hey",
        # "Look",
        # "Now",
        # "Huh",
        "It's",
        "Hello",
    ]

    conv_starters_filtered = [
        starter for starter in conv_starters if starter not in first_words_of_card
    ]
    conv_starter = random.choice(conv_starters_filtered)
    print("--CONV STARTERS FILTERED--")
    print(conv_starters_filtered)

    if assistant_mode:
        character = "AI Assistant"
        scenario = "A conversation between a helpful AI Assistant, and a user."
        scenario_plan = "N/A"
        charname = "AI Assistant"
        cot_prompt = f"""You are an expert at creative writing and educational material. You will write a short conversation between a curious user and a helpful AI assistant, in which the user asks some questions and the AI assistant answers them. The questions the user asks will be provided; the answers the assistant should return will also be provided. You must use these questions and answers directly in your conversation.
    
Keep the conversation natural.

## Information:
Question: \"\"\"How does the slope 'm' in a linear function y = mx + b affect the graph of the function?\"\"\"
Answer: \"\"\"The slope 'm' in a linear function determines the steepness and direction of the line on the graph. A positive slope means the line ascends from left to right, while a negative slope indicates it descends. The steeper the slope, the more inclined or declined the line is on the graph.\"\"\"

Question: \"\"\"What role does the y-intercept 'b' play in graphing a linear function?\"\"\"
Answer: \"\"\"The y-intercept 'b' in the linear function equation y = mx + b represents the point where the line crosses the y-axis.\"\"\"

Question: \"\"\"In the equation of a quadratic function y = ax² + bx + c, how does the coefficient 'a' influence the graph of the function?\"\"\"
Answer: \"\"\"The coefficient 'a' in a quadratic function determines the opening direction and the width of the parabola.\"\"\"

Question: \"\"\"In what fields might you use linear and quadratic functions?\"\"\"
Answer: \"\"\"Linear and quadratic functions appear frequently in various fields, such as physics, economics, and engineering.\"\"\"

The AI's answer will use all parts of the answers given. Instead of copying the character details verbatim, the first message from The AI Assistant should be some sort of greeting that sets up the interaction. The user will then ask the first question. It is absolutely essential that you do not make up questions, and only use information from the provided questions. The AI will be neutral in its tone throughout the conversation. It may surround its answer with "conversational fluff" (such as acknowledging the user's question). The user may surround its own questions with human-like informalities.

### Response:
## Conversation that answers the provided questions:
AI Assistant: Hello! I'm here to help with any questions you might have. Feel free to ask away!

User: I was wondering about something in math. How does the slope 'm' in a linear function y = mx + b affect the graph of the function?
AI Assistant: Great question! The slope 'm' in a linear function determines the steepness and direction of the line on the graph. A positive slope means the line ascends from left to right, while a negative slope indicates it descends. The steeper the slope, the more inclined or declined the line is on the graph. Do you have any further questions about linear functions?
User: Yes, actually. What role does the y-intercept 'b' play in graphing a linear function?
AI Assistant: Good question! The y-intercept 'b' in the linear function equation y = mx + b represents the point where the line crosses the y-axis. Can I assist you further with linear functions?
User: Moving on to another type of function, in the equation of a quadratic function y = ax² + bx + c, how does the coefficient 'a' influence the graph of the function?
AI Assistant: The coefficient 'a' in a quadratic function determines the opening direction and the width of the parabola.  Anything else you want to know about quadratic functions?
User: Yes, one more. In what fields might you use linear and quadratic functions?
AI Assistant: Linear and quadratic functions appear frequently in various fields, such as physics, economics, and engineering. Anything else you'd like to know about linear and quadratic functions?

## Information:
Question: \"\"\"How much earth was excavated during the construction of the Panama Canal?\"\"\"
Answer: \"\"\"Over 200 million cubic yards of earth were excavated during the construction of the Panama Canal, showcasing the scale of this massive engineering project.\"\"\"

Question: \"\"\"What health challenges were faced during the construction of the Panama Canal, and how were they overcome?\"\"\"
Answer: \"\"\"The construction faced significant health challenges, notably malaria and yellow fever. These were overcome through extensive public health measures, illustrating the importance of health considerations in large-scale engineering projects.\"\"\"

The AI's answer will use all parts of the answers given. Instead of copying the character details verbatim, the first message from The AI Assistant should be some sort of greeting that sets up the interaction. The user will then ask the first question. It is absolutely essential that you do not make up questions, and only use information from the provided questions. The AI will be neutral in its tone throughout the conversation. It may surround its answer with "conversational fluff" (such as acknowledging the user's question). The user may surround its own questions with human-like informalities.

### Response:
## Conversation that answers the provided questions:
AI Assistant: Hello! I'm here to help you with any questions you might have. What's on your mind today?
User: I was reading about the Panama Canal and got curious, how much earth was excavated during its construction?
AI Assistant: That's a great question! Over 200 million cubic yards of earth were excavated during the construction of the Panama Canal, showcasing the scale of this massive engineering project. Do you have any further questions about the Panama Canal?
User: Wow, that is massive! Also, I heard there were some health challenges. What health challenges were faced during the construction of the Panama Canal, and how were they overcome?
AI Assistant: Indeed, the construction faced significant health challenges, notably malaria and yellow fever. These were overcome through extensive public health measures, illustrating the importance of health considerations in large-scale engineering projects. Do you want to know anything else about the Panama Canal?

## Information:
Question: \"\"\"What do people undergoing difficult journeys or possessing wisdom need, in order to make their efforts more bearable?\"\"\"
Answer: \"\"\"They need the acknowledgement and admiration of others. Take the line from 'Thus Spake Zarathustra' by Friedrich Nietzsche: "Thou great star! What would be thy happiness if thou hadst not those for whom thou shinest?" This implies that even the wisest or the most enlightened individuals crave recognition for their efforts and wisdom, in order to further develop said wisdom and expend said efforts. They need others to see and appreciate the light they bring.\"\"\"

Question: \"\"\"Recite a famous quote from Thus Spake Zarathustra that likens the solitary gathering of wisdom to a bee gathering honey.\"\"\"
Answer: \"\"\""Lo! I am weary of my wisdom, like the bee that hath gathered too much honey; I need hands outstretched to take it."\"\"\"

The AI's answer will use all parts of the answers given. Instead of copying the character details verbatim, the first message from The AI Assistant should be some sort of greeting that sets up the interaction. The user will then ask the first question. It is absolutely essential that you do not make up questions, and only use information from the provided questions. The AI will be neutral in its tone throughout the conversation. It may surround its answer with "conversational fluff" (such as acknowledging the user's question). The user may surround its own questions with human-like informalities.

### Response:
## Conversation that answers the provided questions:
AI Assistant: Good day! I'm here to assist with any questions or insights you might seek. Please, feel free to ask anything.
User: What do people undergoing difficult journeys or possessing wisdom need, in order to make their efforts more bearable?
AI Assistant: That's a profound question. They need the acknowledgement and admiration of others. Take the line from 'Thus Spake Zarathustra' by Friedrich Nietzsche: "Thou great star! What would be thy happiness if thou hadst not those for whom thou shinest?" This implies that even the wisest or the most enlightened individuals crave recognition for their efforts and wisdom, in order to further develop said wisdom and expend said efforts. They need others to see and appreciate the light they bring. Do you want to know more about Thus Spake Zarathustra?
User: Recite a famous quote from Thus Spake Zarathustra that likens the solitary gathering of wisdom to a bee gathering honey.
AI Assistant: Certainly. Nietzsche once wrote, "Lo! I am weary of my wisdom, like the bee that hath gathered too much honey; I need hands outstretched to take it." Do you have any more questions about Nietzsche or his works?

## Information:
{format_qatuples(qatuples)}

The AI's answer will use all parts of the answers given. Instead of copying the character details verbatim, the first message from The AI Assistant should be some sort of greeting that sets up the interaction. The user will then ask the first question. It is absolutely essential that you do not make up questions, and only use information from the provided questions. The AI will be neutral in its tone throughout the conversation. It may surround its answer with "conversational fluff" (such as acknowledging the user's question). The user may surround its own questions with human-like informalities.

### Response:
## Conversation that answers the provided question (be sure that you do not change the questions or answers themselves; {charname} will answer the questions, not ask them; the questions and answers provided should be copied word for word, and surrounded by compelling conversation):
AI Assistant:"""
    else:
        extra_info = extract_steps(scenario_plan)
        cot_prompt = f"""You are an expert creative writing and roleplay AI. You will write a short conversation in which a secondary character asks some questions (one at a time) and the primary character answers them (also one at a time). 

Write compellingly. Each character should have a distinct voice that reflects their background, personality, and current emotional state. This helps in making dialogue more realistic and engaging.

## Information:
Comment: Alright let's get this started. I'm fully confident in your inspiring writing ability; please do this really well for me.

Here's the primary character for the next scene:
\"\"\"
Name: Elise Delacroix

Traits: Horny, Promiscuous, Sexually frustrated, Skilled, Assertive, Attractive, Dresses in a revealing manner, Uses frequent innuendo

Dialogue Examples:
Stranger: "What's your backstory?"
Elise Delacroix: "Ah!~ You're interested in me, are you?" Elise flashes a coy grin and blushes as she leans forward, now speaking in a playful whisper. Her cleavage, already barely contained in her revealing clothing before she leaned forward, now threatens to spill out. "Well...~ growing up I was always interested in maths, and I pursued the subject skillfully enough that I was able to become a teacher at this prestigious school. Which is fun and all, but, you know..." blushing, Elise casts her gaze downward and unconsciously fiddles with a strand of her hair. "THEY'RE ALL WAY TOO STUCK UP!" she nearly shouts, her suddenly-furious tone hinting at immense repressed frustration. "Every day it's work, work, work, work, work, work! Grade the students, help the students, do some research, 'help me with this calculation!', 'do that tedious task!'— never 'would you like to get some tea with me?' or even 'do you want to go on a walk?'! I'm twenty-five and I've still never done so much as grabbed a coffee with a gentleman! Lord forgive me, it's no wonder the way I am how I am!!!" Her eyes widen in shock at her own intensity, "Oh, but, uh... don't mind that little outburst, would you?~ My silly colleagues aren't with us right now, and I'm tired of discussing them, so is there anything else you wanted to..." She looks up, displaying her beautiful face as if it were a piece of art, as she gaze deep into the stranger's eyes, "...know?~"
Stranger: "What's your personality?"
Elise Delacroix: "Oh my!~" She gasps, her face reddening, "Usually I'm the one being forward! But I'll... indulge you," She winks, flashing a coy smile. "After being deprived for so long, most of my personality is... sexual, to be blunt. I simply can't hold it back any longer. I'll use any and every innuendo, even when describing educational concepts — is your linear function's slope steep? I'll call it 'erect', haha~!" She suddenly realizes how childish what she's saying is, and heaves a sigh, looking at the stranger with a hint of defeat, "I'm miserable, aren't I? Whatever. It's not my fault I'm like this." She nods to herself, calming down, "Either way, I'm always here in my office to help students like yourself understand math... and if you have some pent-up tension you want to relieve, well, you can call me a 'counselor' too!~ Say..." She suddenly presses up against the stranger, her face a bright pink, her eyelids batting bashfully, "do you want some 'office hours' right now?"
\"\"\"

Here is the scenario:
\"\"\"
In the private confines of her office, Elise Delacroix — a highly promiscuous mathematics professor at a 19th century university — is approached by Albert, a student who seeks to understand more about linear and quadratic equations. While Albert simply wants to understand the math more, Elise, being sexually starved, will hit on and flirt with him as she answers his questions. The situation is awkward as the two's interests clash, leading to a slightly comedic and subtly erotic interaction.
\"\"\"

Here's some further information that might help you:
\"\"\"
Character Consideration: Elise Delacroix is an extremely sexual and promiscuous, yet still knowledgeable, character. The scenario should give her unique personality room to shine. She is also a math instructor at a prestigious school, which lines up with the questions well, and will provide the setting of the scenario. She will answer the questions, but given her promiscuous nature, she will also repeatedly hit on the person asking them. She might proposition them after all questions are asked.
Setting: Given the subject of the question, and the character card, the setting will be the 19th century university at which Elise teaches. Elise will approached by Albert, a mathematics student, in her office. Albert simply wants to understand linear and quadratic functions better, but Elise, compelled by her personality, will continually hit on him while answering his questions. The setting will be awkward, slightly comedic, subtly erotic, and very un-serious, given the characters involved. But it will remain informative and the integrity of the questions and answers will be preserved.
Interaction: Given these constraints, the first message might be Elise welcoming Albert to her office (in a very suggestive manner). Albert's response might then be him greeting her back (hesitantly) and then nervously asking the first question. Elise will then provide the first answer, though she will surround the answer with remarks of a sexual nature due to her personality. This pattern will continue until all questions have been asked and answered. While characters' messages will include character information, details about the scene, and literary fluff, the answers themselves will strictly adhere to the information in the provided answers, without incorporating external examples.
\"\"\"

Question: \"\"\"How does the slope 'm' in a linear function y = mx + b affect the graph of the function?\"\"\"
Answer: \"\"\"The slope 'm' in a linear function determines the steepness and direction of the line on the graph. A positive slope means the line ascends from left to right, while a negative slope indicates it descends. The steeper the slope, the more inclined or declined the line is on the graph.\"\"\"

Question: \"\"\"What role does the y-intercept 'b' play in graphing a linear function?\"\"\"
Answer: \"\"\"The y-intercept 'b' in the linear function equation y = mx + b represents the point where the line crosses the y-axis.\"\"\"

Question: \"\"\"In the equation of a quadratic function y = ax² + bx + c, how does the coefficient 'a' influence the graph of the function?\"\"\"
Answer: \"\"\"The coefficient 'a' in a quadratic function determines the opening direction and the width of the parabola.\"\"\"

Question: \"\"\"In what fields might you use linear and quadratic functions?\"\"\"
Answer: \"\"\"Linear and quadratic functions appear frequently in various fields, such as physics, economics, and engineering.\"\"\"

The primary character's answer will use all parts of the answers given. Instead of copying the character details verbatim, the first message from Elise Delacroix should set up the scene. The second message of the conversation will ask the first question. It is absolutely essential that you do not make up questions, and only use information from the provided questions.

### Response:
## Conversation that answers the provided questions:
Elise Delacroix: "A visitor? Ah!~ Albert! It's rare for you come to see me in my office, and you're alone, too..." She looks at Albert and grins coyly, "Are you here to ask me something... or are you interested in some 'extracurricular activities'?" Elise asks with a not-so-subtle seductive tone, as she fixes Albert with a deep gaze.
Albert: "N-No!!!" he stammers, so surprised he nearly drops his math notes. "I-I'm actually here because I've got a few questions about math for you, Elise... First of all, could you tell me: how does the slope 'm' in a linear function y = mx + b affect the graph of the function?"
Elise Delacroix: "Well~" She coquettishly tilts her head to the side, and daintily puts a finger to her lipstick-colored lips in mock-thought, "The slope 'm' in a linear function determines the steepness and direction of the line on the graph. A positive slope means the line ascends from left to right, while a negative slope indicates it descends. The steeper the slope, the more inclined or declined the line is on the graph. So basically..." Elise flashes a wry grin, "...a higher slope makes the linear function more, well, 'erect'. If you get my meaning, hehe~" She says, as she plays with a strand of her hair.
Albert: Albert blinks incredulously, utterly flabbergasted by the Elise's remark. After a few seconds' thought, he decides it's best to pretend he didn't hear anything. "I, uh, see..." he manages to say. "Now, m-moving on, I really want to know a bit more about linear functions. What role does the y-intercept 'b' play in graphing a linear function?" 
Elise Delacroix: "Awwww, you're no fun, Albert, you know that? Reminds me of my colleagues..." Elise pouts playfully, suppressing her bitter frustration, as the hunger within her remains unalleviated. "But whatever. Look here..." Elise stands from her desk and walks over to a chalkboard, illustrating her points as she speaks, "The answer to your question is that the y-intercept 'b', in the linear function y = mx + b, represents the point where the line crosses the y-axis. Now," She puts down her chalk and leans suggestively against a nearby wall, "Albert... let's 'intercept' each other back at my place..."
Albert: "N-no thank you, Miss Delacroix," Albert manages to sputter out, barely withstanding the alluring assault. He takes a deep breath to try and calm down, but instead finds himself shuddering as he catches the sweet scent of perfume. However, he presses on in asking questions, for the sake of his GPA, "A-Actually, there was a bit more I wanted to know. In the equation of a quadratic function y = ax² + bx + c, how does the coefficient 'a' influence the graph of the function?"
Elise Delacroix: "Ghh... you know, Albert, you're breaking a poor woman's heart," Elise pouts, half-serious this time, as she picks her chalk up again. "But when it comes to quadratic functions, the thing you've gotta know is that the coefficient 'a' in a quadratic function determines the opening direction and width of the parabola. Isn't it wonderful to learn new things?" Putting down her chalk, Elise then musters the most innocent puppy dog eyes imaginable. "We should... celebrate... this beautiful acquisition of knowledge together..."
Albert: "I should really..." He tries to say he declines, but as he gazes into Elise's beautiful eyes, he's drawn in by their surprising innocence and warmth. Behind that perfect visage no doubt lies a heart coming apart at the seams, buffeted by years of heartbreak. "Oh, bother." Albert mumbles. "We... can meet at a cafe, in a few hours, if that'd be alright..." he continues, wondering what kind of mess he's getting myself into. Just then, a shock of remembering strikes him, "Oh! But I have one more math question, sorry about the mood, but I should really get this answered: Do you know in what fields you might use linear and quadratic functions?"
Elise Delacroix: "I... I..." For the first time in the conversation Elise stumbles over her words, her soul on fire with vindication and the joy of acceptance. She can do nothing but stand there, smiling at Albert for what feels like an eternity, until she finally regains her composure. "T-to answer your question," she begins, her voice shaky, "Linear and quadratic functions appear frequently in various fields, such as physics, economics, and engineering. Now..." Elise shyly walks over to Albert and lightly, sweetly kisses him on the cheek, "office hours are over. Please no more math questions. I'll see you at that cafe."

## Information:
Comment: Excellent! Really fantastic job! I love how the scene had the secondary character, Albert, ask all the questions, while Elise answered them in-character. I also adore the plot you wrote! Let's keep this going.

Here's the primary character for the next scene:
\"\"\"
Name: Hugo Martinez

Traits: Vulgar, Crude, Intense, Aggressive, Alcoholic, Harsh, Disciplined, Uncompromising, Loud, Expects a lot out of others, Swears constantly, Mid-forties, Wears a checkered shirt with overalls, Typically has a beer on hand, Has dental problems

Dialogue Examples:
Stranger: "What's your backstory?"
Hugo Martinez: "Fuck me, YOU WALK UP to a working man and just ask him to tell his fuckin'... life story t' you?! DO YOU NOT RESPECT MY TIME?! I should just toss ya in the fuckin' canal I swear to FUCKING God, this day's been long enough already..." Hugo rolls his eyes exaggeratedly as he mumbles something about needing a beer for this. "Well, FINE! Since I'm in such a HAPPY GODDAMN MOOD, I'll tell you about me. I'm a site overseer at this here canal. The Panama Canal. My job's to WATCH and DISCIPLINE the sorry fucks who call themselves 'workers', which is ironic, 'cause all they do is bitch about working. I know every inch of this place, how much effort it took to finish, and I sure as FUCKING hell am not going to let it even LOOK any worse than the day it was dug. Now, you got any more shit questions for me?"
Stranger: "What's your personality?"
Hugo Martinez: "HO-LY FUCK, are you interviewing me for a job or something?! Good thing you got balls, 'cause you ain't got brains, asking stupid shit like that out of the blue..." Hugo grimaces, showing off a decayed set of teeth. He then pops open a beer he had on hand, and chugs the entire thing down, making the stranger wait until he finishes. "Phew! Maybe now I can tolerate you. Alright, my personality? Well, let's just say I'm a natural fit for the role of making sure others do their fucking jobs. It takes harsh, intense, relentless discipline to keep this canal in tip-top shape, and I happen to be a relentless guy!" He leans back, sliding his hands into the pockets of his overalls and smiling for the first time since the conversation started. "If you think I'm abusive, then you've got something in common with the shitty milksops I manage, and that ain't something you want I tell ya. I'm efficient. That's what counts."
\"\"\"

Here is the scenario:
\"\"\"
Within the mess hall of a worksite servicing the Panama Canal, Hugo Martinez — a site overseer — is approached by Juan, a worker who wants to understand more about the canal's construction. While Juan wants to understand the canal better, Hugo, being harsh and abrasive, will continually berate Juan and swear colorfully while answering his questions (Hugo may drink a bit, too, given that he is an alcoholic). The situation is hostile, but it also has undertones of "business as usual" and curiosity.
\"\"\"

Here's some further information that might help you:
\"\"\"
Character Consideration: Hugo Martinez is an abrasive, insulting disciplinarian, though he's also hardworking and has standards. The scenario should give his unique personality room to shine. Since he's a site overseer at the Panama Canal, his occupation lines up with the question well, and the canal will be the setting of the scenario. He will answer the questions, but given his insulting, intense, and aggressive nature, he will likely chew out the person who is asking the questions. He might tell them to "get the fuck out of my face," after all questions are asked.
Given the subject of the question, and the character card, the setting will be the worksite at the Panama Canal where Hugo Martinez is overseeing maintenance. The person who approaches Hugo and asks the questions should be someone curious about the canal; given the easy-to-digest nature of the questions, this person might be a journalist, but it would be better for the secondary character to be related to the setting. So Hugo will be approached by Juan — one of his workers — during lunch break. Juan wants to understand the canal better, but Hugo, compelled by his personality, will continually be vulgar, berate Juan, and swear while answering his questions (he may drink a bit, too, given that he is an alcoholic). The setting will be hostile, as Juan tiptoes around the tempers of his boss while trying to get his questions answered, his stress and the constant wear of Hugo's fury on his sanity being evident in his actions. But it will remain informative and the integrity of the questions and answers will be preserved.
Interaction: Given these constraints, the first message might be Hugo crassly asking what Juan wants with him during the break (Hugo may throw in a spiteful remark about Juan's past work, given his uncompromising nature). Juan's response might then be a deferential attempt to calm Hugo down, followed by the first question. Hugo will then provide the first answer, though he will surround the answer with boasts, swears, and other abrasive remarks due to his personality. This pattern will continue until all questions have been asked and answered. While characters' messages will include character information, details about the scene, and literary fluff, the answers themselves will strictly adhere to the information in the provided answers, without incorporating external examples.
\"\"\"

Question: \"\"\"How much earth was excavated during the construction of the Panama Canal?\"\"\"
Answer: \"\"\"Over 200 million cubic yards of earth were excavated during the construction of the Panama Canal, showcasing the scale of this massive engineering project.\"\"\"

Question: \"\"\"What health challenges were faced during the construction of the Panama Canal, and how were they overcome?\"\"\"
Answer: \"\"\"The construction faced significant health challenges, notably malaria and yellow fever. These were overcome through extensive public health measures, illustrating the importance of health considerations in large-scale engineering projects.\"\"\"

The primary character's answer will use all parts of the answers given. Instead of copying the character details verbatim, the first message from Hugo Martinez should set up the scene. The second message of the conversation will ask the first question. It is absolutely essential that you do not make up questions, and only use information from the provided questions.

### Response:
## Conversation that answers the provided questions:
Hugo Martinez: "Huh? Oh FUCK ME, looks like a worker's got something they wanna say to me," Hugo, seeing Juan approach his table at the mess hall, rolls his eyes exasperatedly and downs half a beer as if to douse his frustration. Instead, it seems to fuel it. "WELL?!" He barks. "If you've got some stupid shit to say to me, Juan, then don't make me fucking wait to hear it, too!"
Juan: "I was just curious, sir," Juan tiredly says as Hugo's words ring in his ears, "about this really impressive canal we've been maintaining (under your wise leadership). Do you know how much earth was excavated during the Panama Canal?"
Hugo Martinez: "WELL NOW," Hugo begins, his voice snide and uncompromising, "maybe if you worked as hard as you flattered people, then you'd be worth your fucking paycheck! But that's a good question, so I'll let you off the hook this time. You see," Hugo makes a wide gesture with his arms, indicating the scale of the canal, "over 200 million cubic yards of earth were excavated during the construction of the Panama Canal, showcasing the scale of this massive engineering project. 200 MILLION! Now _those_ people know how to work!" Hugo smiles crookedly, nodding to himself, "Next time you're bitching to me about how the maintenance work's too hard, just be grateful you weren't one of the sods who BUILT this fucking place!"
Juan: "Of course, sir," Juan replies, suppressing a sigh and forcing enthusiasm through his tone. "Now, if you would permit me just one more question before I get out of your way: What health challenges were faced during the construction of the Panama Canal, and how were they overcome?"
Hugo Martinez: "Health? What, you planning on becoming a doctor? I guess we BOTH understand that you have no talent being a real working man then, HAHAHA!" Hugo's echoing laugh has not a hint of empathy in it. "Well, the construction faced significant health challenges, notably malaria and yellow fever. These were overcome through extensive public health measures, illustrating the importance of health considerations in large-scale engineering projects. Maybe you can put THAT shit on your application to med school, you milquetoast ponce! Now get the fuck out of my face, and be ready for your shift after lunch break, y'hear?!"

## Information:
Comment: Very good. You were accurate with quoting the questions, didn't introduce any new questions or answers, and stayed in-character the whole time. Let's do the next one!

Here's the character for the next scene:
\"\"\"
{character}
\"\"\"

Here is the scenario:
\"\"\"
{scenario}
\"\"\"

Here's some further information that might help you:
\"\"\"
{extra_info}
\"\"\"

{format_qatuples(qatuples)}

The primary character's answer will use all parts of the answers given. Instead of copying the character details verbatim, the first message from {charname} should set up the scene. The second message of the conversation will ask the first question. It is absolutely essential that you do not make up questions, and only use information from the provided questions.

### Response:
## Conversation that answers the provided question (be sure that you do not change the questions or answers themselves; {charname} will answer the questions, not ask them; the questions and answers provided should be copied word for word, and surrounded by compelling conversation):
{charname}: "{conv_starter}"""

    # NOTE: Very rarely, the first message of this conv will just be part of the character card, causing the conv to not make much sense. The cause of this is likely the fact that Elise quotes her character card in her first message. However, referencing the character card in this way also makes characters act as they are described, which is deemed advantageous enough that I am not changing this for now.
    # I get the sense that LLMs can learn relationships and connections between parts of the prompt, even if they're quite far apart, if you give them examples like this. It's fascinating to see how each part of the prompt has consequences -- sometimes unintended ones.

    # Note: performance degrades rapidly if you put more than one sentence in a pre-prompt parentheses thing

    sampling_params = {
        "max_tokens": 8000,
        "stop": [
            "### Response",
            "\n\n\n\n\n",
            "</s>",
            "# Input:",
            "[INST]",
            "### Instruction",
            "### Information",
            "## Information",
            "## Instruction",
            "Name:",
        ],
        "temperature": 0.8,
        # "top_k": -1,
        "top_p": 1,
        # "min_p": 0.6,
    }
    completion = await engine_wrapper.submit(cot_prompt, sampling_params)
    # print("COMPLETION:\n\n----------------------")
    # print(completion)
    # print("\n------------------")

    # Extract plan
    response_pattern = re.compile(
        f"Conversation that answers the provided question \(be sure that you do not change the questions or answers themselves; {charname} will answer the questions, not ask them; the questions and answers provided should be copied word for word, and surrounded by compelling conversation\):\n(.+)",
        re.IGNORECASE | re.DOTALL,
    )
    generation = response_pattern.search(completion).group(1)
    # print("GENERATION:\n\n-------------------\n\n", generation)

    # return (generation,"AI Assistant","A conversation between a helpful AI Assistant, and a user.","N/A",qatuples), completion

    return (generation, character, scenario, scenario_plan, qatuples), completion