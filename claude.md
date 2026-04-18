- use UV instead of pip
- make sure you add adequete test cases for all the core logic (dont add unwanted test cases)
- dont keep adding unwanted comments. comment in necessary critical to understand logic alone inside the function. but add a docstring for all the function (A one or two liner which clearly explains what the function is all about)
- keep code small and consize. avoid unwanted code
- whenever I instruct to change anything in the code, make the corresponding fix in the plan and the corresponding design
- do not use emoji's for writing. I hate them. do not use emojis
- function names has to be clear and convey what exactly they are doing. it should not be ambiguous.
- use pydantic for struct serialization and de-serialization
- no hardcoding values in code, it should be config or enums appropriately
- if a function or peace of code is not used after I do manual review, remove the code.
- no hardcoding
- json needs to be created using pydantic models not string manipulation
- log all the errors properly (use a temporal log suit for error logging for easy observability)
- on top of every file add/update a docstring for 2-3 lines what the file is all about (dont go into implementation details just clearly explain what the file is responsible for) whenever you are editing a file if needed.


